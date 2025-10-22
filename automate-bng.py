import paramiko
import time

# Configuration for the routers
active_router = {
    'host': '10.10.20.2',  # Replace with your active router's IP
    'username': 'admin',  # Replace with your username
    'password': 'admin'     # Replace with your password
}

backup_router = {
    'host': '10.10.30.2',  # Replace with your backup router's IP
    'username': 'admin',  # Replace with your username
    'password': 'admin'     # Replace with your password
}

# Function to ping from the active router
def ping_router_from_active():
    try:
        # Establish SSH connection to the active router
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(active_router['host'], username=active_router['username'], password=active_router['password'])

        # Execute the ping command (adjust the command as needed)
        command = 'ping 192.168.1.2 count=10 interval=0.5'  # Replace with the target IP you want to ping
        stdin, stdout, stderr = ssh.exec_command(command)

        # Read the output
        output = stdout.read().decode()
        print(output)  # Print the output for debugging

        # Check for failure: "received=0 packet-loss=100%"
        if "received=0" in output and "packet-loss=100%" in output:
            return False, output  # Indicates that the ping failed
        return True, output  # Indicates that the ping was successful

    except Exception as e:
        print("An error occurred while connecting to the active router: {}".format(e))
        return False, ""

    finally:
        ssh.close()

# Function to activate a port on the backup router
def activate_port_on_backup():
    try:
        # Establish SSH connection to the backup router
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(backup_router['host'], username=backup_router['username'], password=backup_router['password'])

        # Command to activate the port (replace 'ether2' with your actual port)
        command = 'interface enable ether2'  # Adjust the command as needed
        stdin, stdout, stderr = ssh.exec_command(command)

        # Print output and errors
        print(stdout.read().decode())
        print(stderr.read().decode())

    except Exception as e:
        print("An error occurred while connecting to the backup router: {}".format(e))

    finally:
        ssh.close()

# Function to disable a port on the backup router
def disable_port_on_backup():
    try:
        # Establish SSH connection to the backup router
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(backup_router['host'], username=backup_router['username'], password=backup_router['password'])

        # Command to disable the port (replace 'ether2' with your actual port)
        command = 'interface disable ether2'  # Adjust the command as needed
        stdin, stdout, stderr = ssh.exec_command(command)

        # Print output and errors
        print(stdout.read().decode())
        print(stderr.read().decode())

    except Exception as e:
        print("An error occurred while connecting to the backup router: {}".format(e))
        
    finally:
        ssh.close()

# Main logic
if __name__ == "__main__":
    backup_active = False  # Track if the backup router's port is active
    while True:
        print("Pinging from active router...")
        ping_success, output = ping_router_from_active()
        
        if not ping_success:
            if not backup_active:
                print("Active router is down. Activating backup router...")
                activate_port_on_backup()
                backup_active = True
        else:
            # Check if ping is successful (e.g., "sent=10 received=10 packet-loss=0%")
            if "sent=10" in output and "received=10" in output and "packet-loss=0%" in output:
                if backup_active:
                    print("Active router is back up. Disabling backup router...")
                    disable_port_on_backup()
                    backup_active = False
            print("Active router is up.")

        time.sleep(10)  # Wait before the next ping attempt
