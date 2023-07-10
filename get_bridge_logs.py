"""
Interactive script to pull archiver logs for both stream and bridge sources to local directory stored in the root of the
script environment.

Original code author(s): Jeffry Ratcliff, Jonathan Wilson
Updated code author: Zack Waits
"""

__author__ = "Zack Waits"
__credits__ = ["Jeffry Ratcliff", "Jonathan Wilson"]
__version__ = "0.0.2"
__maintainer__ = "Zack Waits"
__email__ = "zwaits@een.com"
__status__ = "Alpha"

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
from time import time,perf_counter
from typing import Optional

import requests


@dataclass
class DeviceInfo:
    esn: str
    type: str
    name: str
    cluster: str
    disk_ips: {}
    archivers: []
    archiver_states: {}

class ArchiverBridgeLogRetriever(object):
    # Implementation to have API key saved to local environment variable
    #API_KEY = os.environ.get("EEDEV_API_KEY")

    def __init__(self, username:str, password:Optional[str]=None):
        self.auth_base_url = ""
        self.auth_key = ""
        self.token = ""
        self.user_data = {}
        self.username = username
        #self.api_key = VmsActions.API_KEY
        self.authent_url = "/g/aaa/authenticate"
        self.author_url = "/g/aaa/authorize"
        self.base_url = "https://login.eagleeyenetworks.com"
        self.session = self.authenticate(self.username, password)

    def authenticate(self, username=str, password:Optional[str]=None):
        """
        POST request to '/g/aaa/authenticate' to generate the token necessary for the subsequent authorization call.

        PARAMS:
            username: str = Email of account in VMS
            password: str = Password of account in VMS - Defaults to None if not provided, and user is prompted for
                password. Uses getpass to prevent entry from appearing on screen.

        RETURNS:
            Session object initialization of VmsActions class object.
        """
        # Performance timer start
        deltastart = perf_counter()

        # Start session
        self.session = requests.Session()

        # Store username
        self.username = username

        # Prompt for password if not provided
        if password == None:
            password = getpass(f"Enter password for {self.username}: ")

        # Create parameters for authentication post
        print(f"Attempting (simple) login: {self.username}...")
        payload = {"username": self.username,
                   "password": password,}
                   #"A": self.api_key}

        # Post to get token
        r = self.session.post(
            self.base_url + self.authent_url, params=payload, timeout=15)

        # TODO: Logger entry for code response

        # Raise for error if status non-2XX
        if r.raise_for_status() == None:
            print(f"Successful authentication - {r.status_code}")

        # Convert response to json and parse to save token information

        payload = {"token": r.json()["token"]}

        # Performance timer end
        deltastop = perf_counter()

        # Time to complete authentication
        print(f"Completed authentication process: {(deltastop - deltastart)} secs")
        self.authorize(payload)
        return self.session

    def authorize(self, payload):
        """
        POST request for authorization to '/g/aaa/authorize' utilizing token from authenticate method to generate
        'auth_key' cookie. Updates the authenticated URL for the user account.

        PARAMS:
            payload: dict = 'token': str

        RETURNS:
            None
        """
        # Start performance timer
        deltastart = perf_counter()

        r = self.session.post(self.base_url + self.author_url, data=payload, timeout=30)

        # Raise for error if status non-2XX
        r.raise_for_status()

        print(f"Simple Auth w/ Token : {r.status_code}")

        # Save auth_key cookie to object properties
        self.auth_key = r.cookies['auth_key']

        # Grab user settings and data - Not used currently
        self.user_data = r.json()

        # Stop performance timer
        deltastop = perf_counter()

        # Update authorized url for requests
        self.auth_base_url = f"https://{self.user_data['active_brand_subdomain']}.eagleeyenetworks.com"

        # Time to complete full authorization
        print(f"Complete authorization process: {(deltastop - deltastart)} secs")

    def get_device_info(self, esn: str):
        """
        GET request to Nexus to pull down archiver information about the bridge

        PARAMS:
            esn: str = Bridge ESN

        RETURNS:
            di: dict = Dataclass DeviceInfo
        """
        url = 'https://nexus.aus1hub1.eencloud.com/api/v2/EsnDetails/' + esn
        print(f'\nRequesting data from: {url}')
        with self.session as s:

            try:
                response = s.get(url, cookies={'auth_key':self.auth_key, 'vbsadmin_sessionid':self.auth_key})
                print(response.content)

                if not response.ok:
                    print(f'Unable to retrieve device info. Response: {response.status_code}')

                    if response.status_code == 403:
                        print(f'Unauthorized. Please ensure you are connected to the EagleEye VPN.')

                    sys.exit(1)

                else:
                    json_response = response.json()
                    json_result = json_response['data'][0]

                    di = DeviceInfo
                    di.esn = json_result['esn']
                    di.type = json_result['type']
                    di.name = json_result['name']
                    di.cluster = json_result['cluster']
                    di.disk_ips = json_result['disks_ips']

                    a_list = []
                    for k in dict(json_result['disks_ips']).keys():
                        a_list.append(k)

                    di.archivers = a_list

                    a_states = {}
                    for a in di.archivers:
                        a_states.update({a: json_result['states'][a]['state']})

                    di.archiver_states = a_states

                    return di

            except IndexError:
                print("Invalid result. Check ESN.")
                sys.exit(1)

            except Exception as e:
                print(f'Exception raised when attempting to connect to {url}\nException: {e}')
                sys.exit(1)

    def create_dirs(self, bridge_esn: str):
        """
        Creates local directory to store the downloaded log files, typically stored in the root folder of the script/repo

        PARAMS:
            bridge_esn: str = bridge ESN, partial of the naming convention used for the filename.
                Syntax is f'{bridge_esn}.{archiver}_{source}.log'
                EX: 100bbc9c.a1471_bridge.log

        RETURNS:
            None
        """
        try:
            script_dir = os.path.dirname(__file__)
            bridge_logs_root_dir = os.path.join(script_dir, "bridge_logs")
            bridge_esn_dir = os.path.join(bridge_logs_root_dir, bridge_esn)

            if not os.path.exists(bridge_logs_root_dir):
                os.mkdir(bridge_logs_root_dir)

            if not os.path.exists:
                os.mkdir(bridge_esn_dir)

        except Exception as e:
            print(f'Error. Unable create requisite directories. Exception:\n{e}')

    def pull_logs(self, di: DeviceInfo, a: int, st: datetime, et: datetime):
        """
        GET to http://{archiver}.eagleeyenetworks.com:28080/query/camera_logs to pull down logs based on the following
        criteria: bridge ESN, start and end times, and specified archiver

        PARAMS:
            di: dict = Dataclass DeviceInfo
            a: int = Archiver selection, based on list index
            st: datetime = start time
            et: datetime = end time

        RETURNS:
            None - Outputs to file, local dir created in root of script location.
        """
        # Jeff's Code
        def convert_dt_to_een_time(dt: datetime):
            return dt.strftime('%Y%m%d%H%M%S.%f')[:18]

        self.create_dirs(di.esn)
        st = convert_dt_to_een_time(st)
        et = convert_dt_to_een_time(et)
        archiver_name = di.archivers[a]

        for t in ['bridge', 'stream', 'analog', 'preview']:
            t0 = time()
            query_params = dict(c=di.esn,
                                t=st,
                                e=et,
                                q='none',
                                l=t)

            url = 'http://{0}.eagleeyenetworks.com:28080/query/camera_logs'.format(di.archivers[a])
            print('Fetching {0} logs for {1}'.format(t, di.esn))
            log_response = requests.get(url, query_params, stream=True, cookies={'auth_key':self.auth_key, 'vbsadmin_sessionid':self.auth_key}, timeout=240)

            if log_response.status_code == 200:
                log_path = os.path.join('.', f'bridge_logs/{di.esn}.{archiver_name}_{t}.log')

                count = 0
                with open(log_path, "w") as f:
                    output_busy_queue = ['|', '/', '-', '\\']
                    sys.stdout.write('.')

                    for line in log_response.iter_lines():
                        f.write(str(line) + '\n')

                        if count % 10 == 0:
                            p_char = output_busy_queue.pop(0)
                            output_busy_queue.append(p_char)
                            sys.stdout.write('\b')
                            sys.stdout.write(p_char)
                            sys.stdout.flush()
                        count += 1

                sys.stdout.write('\b')
                print('  {0} {1} lines'.format(log_path, count))

            else:
                print('  {0} {1}'.format(log_response.status_code, log_response.content))

            print('  Took {0:0.2f} seconds'.format(time() - t0))


if __name__ == "__main__":
    username = "maheshgouda@een.com"
    password = getpass("Enter password: ")
    bridge_esn = input("Enter bridge ESN: ")

    account = ArchiverBridgeLogRetriever(username, password)
    device_info = account.get_device_info(bridge_esn)
    print(f"""
        Device Info:
            ESN: {device_info.esn}
            TYPE: {device_info.type}
            NAME: {device_info.name}
            CLUSTER: {device_info.cluster}
            ARCHIVER_STATES: {device_info.archiver_states}\n""")

    print("Please select archiver (or '0' to exit):")
    i = 1
    for a in device_info.archivers:
        print(f'    {i} : {a}')
        i += 1

    wait_for_input = True
    while wait_for_input:
        a_selection = input("    Archiver selection: ")

        try:
            a_selection = int(a_selection)

            if int(a_selection) == 0:
                print("Exiting...")
                sys.exit(0)

            if a_selection not in range(len(device_info.archivers) + 1):
                raise IndexError

            wait_for_input = False

        except Exception as e:
            print("Please make a valid section.")
            continue

    # User specified start date & time.
    print('\nStart Date & Time Selection')
    wait_for_input = True
    while wait_for_input:
        try:
            i_start_date = input("    Please enter start date in YYYYMMDD format: ")
            i_start_time = input("    Please enter the start time in HHMM format (24-hour clock): ")

            start_dt = datetime.strptime(i_start_date+i_start_time, "%Y%m%d%H%M")
            print(f'    Start time: {start_dt}')
            wait_for_input = False

        except Exception as e:
            print('Error converting start time to datetime object. Please check inputs.')
            continue

    # User specified end date & time.
    print('\nEnd Date & Time Selection')
    wait_for_input = True
    while wait_for_input:
        try:
            i_end_date = input("    Please enter end date in YYYYMMDD format (or enter 'c' for current date & time): ")
            if i_end_date.lower() == 'c':
                end_dt = datetime.utcnow()
                wait_for_input = False

            else:
                i_end_time = input("    Please enter the end time in HHMM format (24-hour clock): ")
                end_dt = datetime.strptime(i_end_date+i_end_time, "%Y%m%d%H%M")

            print(f'    End time: {end_dt}')
            wait_for_input = False

        except Exception as e:
            print('Error converting end time to datetime object. Please check inputs.')
            continue

    account.pull_logs(device_info, a_selection-1, start_dt, end_dt)
    sys.exit(0)
