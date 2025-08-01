# update_dynamic_ipv4_at_cloudflare.py

r"""————————————————————————————————————————————————————————————————————————————
Features:
	1. Validates the router's public IP format using ipify API.
	2. Ensures all predefined constants in the `.env` file are present.
	3. Safely updates the router's public IP in the `.env` file.
	4. Updates DNS records on Cloudflare with robust error handling.
	5. Prints exceptions and continues execution in an infinite loop.
	6. No rate limiting as Cloudflare API call frequency is low.
————————————————————————————————————————————————————————————————————————————"""

import os, time, ipaddress, json
import requests			 					# requests==2.32.4
from dotenv import load_dotenv				# python-dotenv==1.1.1
from datetime import datetime, timezone

load_dotenv()

CloudFlareApiToken	= os.getenv("CloudFlareApiToken")
DnsZoneID			= os.getenv("DnsZoneID")
DnsRecordIdWWW		= os.getenv("DnsRecordIdWWW")
DnsRecordIdRdp		= os.getenv("DnsRecordIdRdp")
DnsRecordIdSftp		= os.getenv("DnsRecordIdSftp")
RouterPublicIp		= os.getenv("RouterPublicIp")
SleepDuration		= float(os.getenv("SleepDuration"))

#———————————————————————————————————————————————————————————————————————————————

def validate_env_variables():

	required_keys = [
		"CloudFlareApiToken",
		"DnsZoneID",
		"DnsRecordIdWWW",
		"DnsRecordIdRdp",
		"DnsRecordIdSftp",
		"RouterPublicIp",
		"SleepDuration",
	]

	missing_vars = [
		var for var in required_keys
		if not os.getenv(var)
	]

	if missing_vars:

		raise ValueError(
			f"Missing required environment variables: "
			f"{', '.join(missing_vars)}"
		)

#———————————————————————————————————————————————————————————————————————————————
# https://www.ipify.org/
#———————————————————————————————————————————————————————————————————————————————
# You should use ipify because:
#	You can use it without limit even if
#	you're doing millions of requests per minute.
#———————————————————————————————————————————————————————————————————————————————

def get_public_ip_of_the_router(
) -> str:

	try:

		response = requests.get(
			"https://api.ipify.org"		# IPv4 by definition
		)
		response.raise_for_status()
		ip = response.text.strip()

		try:   ipaddress.IPv4Address(ip)
		except ipaddress.AddressValueError:

			raise ValueError(
				f"Invalid IPv4 address received: {ip}"
			)

		return ip

	except requests.exceptions.RequestException as e:

		raise RuntimeError(
			f"Failed to fetch public IP: {e}"
		)

	except Exception as e:
		
		raise RuntimeError(
			f"An unexpected error occurred: {e}"
		)

#———————————————————————————————————————————————————————————————————————————————

def update_env_variable(
	file_path: str,
	key:	   str,
	new_value: str,
):

	lines = []
	updated = False

	try:

		# Read the entire file and store the original content in memory
		with open(file_path, "r") as file:

			original_content = file.readlines()  # Preserve original content

			for line in original_content:

				stripped_line = line.strip()

				# Preserve lines without '=' (likely comments or empty lines)
				if '=' not in stripped_line:

					lines.append(line)
					continue

				# Split the line into key, value, and optional comment
				parts = line.split("=", 1)		# Preserve original spacing
				current_key = parts[0].rstrip()	# Preserve spacing before '='

				if current_key.strip() == key:

					# Update the value and remove any existing inline comment
					new_line = f"{current_key}={new_value}\n"
					lines.append(new_line)
					updated = True

				else:

					lines.append(line)

			# If the key was not found, append it at the end
			if not updated:

				lines.append(f"{key}={new_value}\n")

		# Write the updated lines back to the file
		with open(file_path, "w") as file:

			file.writelines(lines)

	except Exception as e:

		# Restore the original content in case of an exception
		with open(file_path, "w") as file:

			file.writelines(original_content)

		raise RuntimeError(
			f"Failed to update .env file: {e}"
		)

#———————————————————————————————————————————————————————————————————————————————

def update_dns_record_ip(
	api_token: str,
	name:	   str,
	zone_id:   str,
	record_id: str,
	ip:		   str,
	proxied:   bool
):

	try:

		url_get = (
			f"https://api.cloudflare.com/client/v4/"
			f"zones/{zone_id}/dns_records/{record_id}"
		)

		headers = {
			"Authorization": f"Bearer {api_token}",
			"Content-Type": "application/json",
		}

		response_get = requests.get(url_get, headers=headers)

		if response_get.status_code != 200:
			
			raise Exception(
				f"Failed to fetch DNS record: "
				f"{response_get.status_code} - {response_get.text}"
			)

		current_record = response_get.json()["result"]

		if (
			current_record["content"] == ip
			and current_record["proxied"] == proxied
		):
			
			# DNS record is already up-to-date.
			return current_record

		url_update = (
			f"https://api.cloudflare.com/client/v4/"
			f"zones/{zone_id}/dns_records/{record_id}"
		)

		data = {
			"type":	   "A",
			"name":	   name,
			"content": ip,
			"ttl":	   1,
			"proxied": proxied,
		}

		response_update = requests.put(
			url_update,
			json	= data,
			headers = headers
		)

		if response_update.status_code != 200:

			raise Exception(
				f"Failed to update DNS record: "
				f"{response_update.status_code} - {response_update.text}\n"
				f"URL: {url_update}\nData: {data}"
			)

		return response_update.json()

	except Exception as e:

		raise RuntimeError(
			f"An unexpected error occurred in update_dns_record_ip: {e}"
		)

#———————————————————————————————————————————————————————————————————————————————

def update_dns_ip_all(
	router_known_public_ip: str,
	env_path: str = '.env'
):

	global RouterPublicIp

	router_cur_public_ip = get_public_ip_of_the_router()

	if (router_cur_public_ip != router_known_public_ip):

		print(
			f"[{datetime.now(timezone.utc).isoformat()}]\n"
			f"The public IP of the router changed\n"
			f"from: {router_known_public_ip}\n"
			f"to:   {router_cur_public_ip}"
		)

		update_env_variable(
			file_path = env_path,
			key = "RouterPublicIp",
			new_value = router_cur_public_ip,
		)

		load_dotenv(override=True)
		RouterPublicIp = os.getenv("RouterPublicIp")

		print(
			json.dumps(
				update_dns_record_ip(
					api_token = CloudFlareApiToken,
					name	  = "www",
					zone_id	  = DnsZoneID,
					record_id = DnsRecordIdWWW,
					ip		  = router_cur_public_ip,
					proxied	  = True
				),
				indent = 4
			)
		)
		print(
			json.dumps(
				update_dns_record_ip(
					api_token = CloudFlareApiToken,
					name	  = "rdp",
					zone_id	  = DnsZoneID,
					record_id = DnsRecordIdRdp,
					ip		  = router_cur_public_ip,
					proxied	  = False
				),
				indent = 4
			)
		)
		print(
			json.dumps(
				update_dns_record_ip(
					api_token = CloudFlareApiToken,
					name	  = "sftp",
					zone_id   = DnsZoneID,
					record_id = DnsRecordIdSftp,
					ip		  = router_cur_public_ip,
					proxied	  = False
				),
				indent = 4
			)
		)
		print('')

#———————————————————————————————————————————————————————————————————————————————

if __name__ == "__main__":

	try:

		while True:

			try:

				validate_env_variables()
				update_dns_ip_all(
					router_known_public_ip = RouterPublicIp
				)
				time.sleep(SleepDuration)

			except Exception as e:

				print(
					f"{e}",
					end	  = '\n\n',
					flush = True,
				)

	except KeyboardInterrupt:

		print(
			f"Received Ctrl+C",
			flush = True,
		)