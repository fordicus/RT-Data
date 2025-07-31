# update_dynamic_ipv4_at_cloudflare.py

import os, requests             # requests==2.32.4
from dotenv import load_dotenv	# python-dotenv==1.1.1

load_dotenv()
CloudFlareApiToken = os.getenv("CloudFlareApiToken")
DnsZoneID		   = os.getenv("DnsZoneID")
DnsRecordAID	   = os.getenv("DnsRecordAID")
YourDomain		   = os.getenv("YourDomain")

def get_public_ip():

	return requests.get(
		"https://api.ipify.org"
	).text

def update_dns_record(ip):
	
	url = (
		f"https://api.cloudflare.com/client/v4/zones/"
		f"{DnsZoneID}/dns_records/{DnsRecordAID}"
	)
	headers = {
		"Authorization": f"Bearer {CloudFlareApiToken}",
		"Content-Type": "application/json",
	}
	data = {
		"type":	   "A",
		"name":	   YourDomain,
		"content": ip,
		"ttl":	   1,
		"proxied": True,
	}
	response = requests.put(
		url,
		json	= data,
		headers = headers
	)
	return response.json()

if __name__ == "__main__":
	
	print(
		update_dns_record(
			get_public_ip()
		),
		flush = True,
	)