import paramiko
import time
import yaml
import logging
import sys
from pathlib import Path
from typing import Tuple, Dict
from paramiko.ssh_exception import SSHException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bng_failover.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

class RouterConnection:
    def __init__(self, config: Dict):
        self.host = config['host']
        self.username = config['username']
        self.password = config['password']
        self.port = config.get('port', 22)
        self.timeout = config.get('timeout', 30)

    def execute_command(self, command: str) -> Tuple[bool, str]:
        ssh = paramiko.SSHClient()
        try:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.host, 
                username=self.username,
                password=self.password,
                port=self.port,
                timeout=self.timeout
            )
            stdin, stdout, stderr = ssh.exec_command(command)
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            if error:
                logging.error(f"Command error on {self.host}: {error}")
                return False, error
                
            return True, output

        except Exception as e:
            logging.error(f"Connection error to {self.host}: {str(e)}")
            return False, str(e)
        finally:
            ssh.close()

class BNGFailover:
    def __init__(self, config_path: str):
        self.load_config(config_path)
        self.active_router = RouterConnection(self.config['active_router'])
        self.backup_router = RouterConnection(self.config['backup_router'])
        self.backup_active = False

    def load_config(self, config_path: str) -> None:
        try:
            with open(config_path) as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {str(e)}")
            sys.exit(1)

    def ping_from_active(self) -> Tuple[bool, str]:
        success, output = self.active_router.execute_command(
            self.config['commands']['ping']
        )
        if not success:
            return False, output
        
        # Check ping results
        if "received=0" in output and "packet-loss=100%" in output:
            logging.warning("Ping failed from active router")
            return False, output
        return True, output

    def handle_failover(self) -> None:
        while True:
            try:
                ping_success, output = self.ping_from_active()
                
                if not ping_success:
                    if not self.backup_active:
                        logging.info("Activating backup router...")
                        success, _ = self.backup_router.execute_command(
                            self.config['commands']['activate_port']
                        )
                        self.backup_active = success
                else:
                    if "packet-loss=0%" in output and self.backup_active:
                        logging.info("Primary router recovered, disabling backup...")
                        success, _ = self.backup_router.execute_command(
                            self.config['commands']['disable_port']
                        )
                        self.backup_active = not success

                time.sleep(self.config.get('check_interval', 5))

            except KeyboardInterrupt:
                logging.info("Shutting down BNG failover monitor...")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {str(e)}")
                time.sleep(5)

if __name__ == "__main__":
    config_path = Path(__file__).parent / "bng_config.yaml"
    failover = BNGFailover(str(config_path))
    failover.handle_failover()
