#!/usr/bin/env python3
"""
Copyright (c) 2023 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

__author__ = "Trevor Maco <tmaco@cisco.com>, Rey Diaz <rediaz@cisco.com>"
__copyright__ = "Copyright (c) 2023 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"

import csv
import json

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
from rich.prompt import IntPrompt, Prompt

from config import *

# Set the base URL for the Meraki Dashboard API
base_url = "https://api.meraki.com/api/v1"

# Set the headers for the API request
headers = {
    "X-Cisco-Meraki-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Rich Console Instance
console = Console()

# Make a GET request to the organizations endpoint
response = requests.get(f"{base_url}/organizations", headers=headers)

# If the request was successful, print the list of organizations
if response.status_code == 200:
    organizations = response.json()

    console.print(Panel.fit(f"Organizations"))
    for i, org in enumerate(organizations):
        console.print(f"[blue]{i + 1}[/]. {org['name']}", highlight=False)

    # Prompt the user to select an organization
    selected_org = None
    while selected_org is None:
        try:
            # org_number = int(input("Enter the number of the organization to provision MAC addresses: "))
            org_number = IntPrompt.ask("Enter the [blue]number[/] of the organization to provision MAC addresses")
            selected_org = organizations[org_number - 1]
        except (ValueError, IndexError):
            console.print(f"[red]Invalid selection. Please enter a number between 1 and {len(organizations)}[/].")

    console.print(Panel.fit(f"Networks for [blue]{selected_org['name']}[/]"))

    # Make a GET request to the networks endpoint for the selected organization
    response = requests.get(f"{base_url}/organizations/{selected_org['id']}/networks", headers=headers)

    # If the request was successful, retrieve the list of networks
    if response.status_code == 200:
        networks = response.json()
        console.print("[blue]0[/]. All networks")
        for i, network in enumerate(networks):
            console.print(f"[blue]{i + 1}[/]. {network['name']}", highlight=False)
    else:
        console.print(f"[red]Failed to retrieve networks for {selected_org['name']}.[/] Status code:",
                      response.status_code)
        networks = []

    # Prompt the user to select a network or choose to provision MAC addresses in all networks
    selected_networks = []
    while not selected_networks:
        try:
            network_numbers = Prompt.ask(
                "Enter the [blue]number[/](s) of the network(s) to provision MAC addresses ([b]comma-separated[/])")

            if network_numbers.strip() == "0":
                selected_networks = networks
            else:
                selected_networks = [networks[int(num) - 1] for num in network_numbers.split(",")]

            if not selected_networks:
                console.print("[red]Invalid selection. Please enter a valid number or list of numbers.[/]")
        except (ValueError, IndexError):
            console.print("[red]Invalid selection. Please enter a valid number or list of numbers.[/]")

    # Parse the CSV file and retrieve the MAC addresses and statuses
    mac_statuses = []
    with open(CSV_PATH, "r") as csv_file:
        reader = csv.reader(csv_file)
        next(reader)  # Skip the header row
        for row in reader:
            mac_statuses.append({
                "mac": row[0],
                "status": row[1]
            })

    console.print(Panel.fit(f"Provision MAC Addresses"))

    # Loop through each network and provision MAC addresses based on their status in the CSV file
    for network in selected_networks:
        console.print(f"[blue]{network['name']}[/]:")

        # Get Network Group policies
        response = requests.request('GET', base_url + f"/networks/{network['id']}/groupPolicies", headers=headers)

        if response.status_code == 200:
            policies = response.json()
        else:
            console.print(f"[red]Failed to retrieve group policies for {network}.[/] Status code:",
                          response.status_code)
            continue

        # Build dictionary of group policies and policy id
        group_policies = {}
        for policy in policies:
            group_policies[policy['name']] = policy['groupPolicyId']

        # Loop through each MAC address and update its policy based on the status in the CSV file
        with Progress() as progress:
            mac_progress = progress.add_task("Provisioning MAC Addresses", total=len(mac_statuses), transient=True)
            mac_counter = 1

            for mac_status in mac_statuses:

                progress.console.print(
                    f"- Updating policy for MAC address [blue]{mac_status['mac']}[/] to [yellow]{mac_status['status']}[/] policy ([blue]{mac_counter}[/] of [blue]{len(mac_statuses)}[/])",
                    highlight=False)

                # Update status for Allowed or Blocked Case
                if mac_status['status'] == "Allowed" or mac_status['status'] == "Blocked":
                    payload = {
                        "clients": [{"mac": mac_status['mac']}],
                        "devicePolicy": mac_status['status']
                    }
                else:
                    # check if policy is defined in network
                    if mac_status['status'] in group_policies:
                        group_policy_id = group_policies[mac_status['status']]

                        payload = {
                            "clients": [{"mac": mac_status['mac']}],
                            "devicePolicy": "Group Policy",
                            "groupPolicyId": group_policy_id
                        }
                    else:
                        progress.console.print(
                            f"  - [red]Invalid status/policy for MAC address {mac_status['mac']}.[/] Skipping...")

                        mac_counter += 1
                        progress.update(mac_progress, advance=1)

                        continue

                response = requests.request('POST', base_url + f"/networks/{network['id']}/clients/provision",
                                            headers=headers, data=json.dumps(payload))

                if response.status_code == 201:
                    progress.console.print(f"  - [green]Success![/]")
                else:
                    progress.console.print(
                        f"  - [red]Failed to update {mac_status['mac']} to {mac_status['status']} policy.[/] Status code:",
                        response.status_code)

                mac_counter += 1
                progress.update(mac_progress, advance=1)

        console.print("")

