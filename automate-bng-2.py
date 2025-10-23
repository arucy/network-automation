import paramiko
import time
import logging
import sys
import subprocess
import threading
from typing import Tuple, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bng_failover.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Router configurations
ROUTER_CONFIG = {
    'active_router': {
        'host': '10.10.20.2',
        'username': 'admin',
        'password': 'admin',
        'port': 22,
        'timeout': 30,
        'loopback': '10.10.10.10'  # Add loopback address
    },
    'backup_router': {
        'host': '10.10.30.2',
        'username': 'admin',
        'password': 'admin',
        'port': 22,
        'timeout': 30
    },
    'commands': {
        'ping_test': 'ping 192.168.1.2 count=10 interval=0.5',
        'enable_backup': 'interface set numbers=0 disabled=no',
        'disable_backup': 'interface set numbers=0 disabled=yes'
    },
    'check_interval': 1
}

class RouterManager:
    """Handles SSH connections and command execution for routers"""
    
    def __init__(self, router_config: Dict):
        self.host = router_config['host']
        self.username = router_config['username']
        self.password = router_config['password']
        self.port = router_config['port']
        self.timeout = router_config['timeout']
        self.loopback = router_config.get('loopback', self.host)
        self.ssh_client = None

    def connect(self) -> bool:
        """Establishes SSH connection to router"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                hostname=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                timeout=self.timeout
            )
            logging.info(f"Successfully connected to {self.host}")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to {self.host}: {str(e)}")
            return False

    def execute_command(self, command: str) -> Tuple[bool, str]:
        """Executes command on router and returns result"""
        if not self.ssh_client:
            if not self.connect():
                return False, "Not connected"

        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            output = stdout.read().decode()
            error = stderr.read().decode()

            if error:
                logging.error(f"Command error on {self.host}: {error}")
                return False, error
            return True, output

        except Exception as e:
            logging.error(f"Command execution error on {self.host}: {str(e)}")
            return False, str(e)

    def disconnect(self):
        """Closes SSH connection"""
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None

    def check_loopback_connectivity(self) -> bool:
        """Check if loopback address is reachable using fping"""
        try:
            result = subprocess.run(
                ['fping', '-r', '3', '-t', '500', self.loopback],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            logging.warning("fping not found, using standard ping")
            response = subprocess.run(
                ['ping', '-n', '1', '-w', '500', self.loopback],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return response.returncode == 0
        except Exception as e:
            logging.error(f"Ping error: {str(e)}")
            return False

class BNGFailover:
    """Manages BNG failover between active and backup routers"""

    def __init__(self):
        self.config = ROUTER_CONFIG
        self.active_router = RouterManager(self.config['active_router'])
        self.backup_router = RouterManager(self.config['backup_router'])
        self.backup_active = False
        self.stop_monitoring = False
        self.loopback_monitor_thread = None
        logging.info("BNG Failover Monitor initialized")

    def monitor_loopback(self):
        """Continuous loopback monitoring thread"""
        consecutive_failures = 0
        consecutive_successes = 0
        failure_threshold = 3
        recovery_threshold = 3
        was_down = False
        
        while not self.stop_monitoring:
            is_reachable = self.active_router.check_loopback_connectivity()
            
            if is_reachable:
                consecutive_successes += 1
                consecutive_failures = 0
                if was_down and consecutive_successes >= recovery_threshold:
                    logging.info(f"Loopback {self.active_router.loopback} recovered")
                    was_down = False
                    consecutive_successes = 0
                    # Let main loop handle backup deactivation
                    continue
            else:
                consecutive_failures += 1
                consecutive_successes = 0
                if consecutive_failures >= failure_threshold and not was_down:
                    logging.warning(f"Loopback {self.active_router.loopback} unreachable")
                    self.handle_failover(loopback_failure=True)
                    was_down = True
                    consecutive_failures = 0
            
            time.sleep(1)

    def handle_failover(self, loopback_failure=False):
        """Handle failover based on failure type"""
        if not self.backup_active:
            if loopback_failure:
                logging.warning("Immediate failover due to loopback failure")
                if self.activate_backup():
                    self.backup_active = True
            else:
                # Normal failover process
                if self.activate_backup():
                    self.backup_active = True

    def check_active_router(self) -> Tuple[bool, bool]:
        """Returns (ssh_status, ping_test_status)"""
        if not self.active_router.ssh_client and not self.active_router.connect():
            return False, False

        success, output = self.active_router.execute_command(
            self.config['commands']['ping_test']
        )
        
        if not success:
            return True, False

        ping_success = "received=0 packet-loss=100%" not in output
        return True, ping_success

    def activate_backup(self) -> bool:
        """Activates backup router"""
        success, output = self.backup_router.execute_command(
            self.config['commands']['enable_backup']
        )
        if success:
            logging.info("Backup router activated")
        return success

    def deactivate_backup(self) -> bool:
        """Deactivates backup router"""
        success, output = self.backup_router.execute_command(
            self.config['commands']['disable_backup']
        )
        if success:
            logging.info("Backup router deactivated")
        return success

    def run(self):
        """Main monitoring loop"""
        logging.info("Starting BNG failover monitoring...")
        
        self.loopback_monitor_thread = threading.Thread(target=self.monitor_loopback)
        self.loopback_monitor_thread.daemon = True
        self.loopback_monitor_thread.start()
        
        recovery_count = 0
        recovery_threshold = 3
        
        while True:
            try:
                is_reachable = self.active_router.check_loopback_connectivity()

                if is_reachable:
                    recovery_count += 1
                    if recovery_count >= recovery_threshold and self.backup_active:
                        logging.info("Active router recovered, deactivating backup")
                        if self.deactivate_backup():
                            self.backup_active = False
                        recovery_count = 0
                else:
                    recovery_count = 0

                time.sleep(self.config['check_interval'])

            except KeyboardInterrupt:
                logging.info("Shutting down BNG failover monitor...")
                self.stop_monitoring = True
                self.loopback_monitor_thread.join(timeout=2)
                self.active_router.disconnect()
                self.backup_router.disconnect()
                break
            except Exception as e:
                logging.error(f"Unexpected error: {str(e)}")
                time.sleep(5)

if __name__ == "__main__":
    failover = BNGFailover()
    failover.run()
