import requests
import json
from pprint import pprint
from jnpr.healthbot import HealthBotClient
from jnpr.healthbot import DeviceSchema
from jnpr.healthbot import DeviceGroupSchema

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

aos_username="USER"
aos_password="PASSWORD"
aos_url="https://xx.xx.xx.xx"
device_user="USER"
device_password="PASSWORD"

hb_ip="xxx.xxx.xxx.xxx"
hb_user="USER"
hb_password="PASSWORD"
# Step 1 - Connect to HealthBot and get hbez handle
hb=HealthBotClient(hb_ip,hb_user,hb_password)
hb.open()
# Step 2 - Get AOS API token
tokenreq_body={'username':aos_username,'password':aos_password}
req_header={'accept':'application/json','content-type':'application/json'}
token_res=requests.post(f"{aos_url}/api/aaa/login",headers=req_header,json=tokenreq_body,verify=False)

authtoken=token_res.json()['token']
headers={'AuthToken':authtoken}

# Step 3 - Pull all defined blueprints
blueprintlist=requests.get(f'{aos_url}/api/blueprints',headers=headers,verify=False)

# Step 4 - Iterate over all blueprints(creating different device groups in HB per blueprint)
for blueprint in blueprintlist.json()['items']:
  bpid=blueprint['id']
  bp_name=blueprint['label']
  transtable=bp_name.maketrans("_","-")
  bp_name=bp_name.translate(transtable)
  print(f'Blueprint: {bp_name}')
  # Multiple ways to get the switches via AOS API. I prefer this one as it groups them by role...
  bp_systems=requests.get(f'{aos_url}/api/blueprints/{bpid}/nodes?node_type=system',headers=headers,verify=False)
  systems=bp_systems.json()['nodes']
  
  leafnames=[]
  spinenames=[]
  # Not sure if I can simplify this bit with graphql or not, so for now I need to pull facts from each device agent
  for key,system in systems.items():
    if system['role'] == 'spine' or system['role'] == 'leaf':
        switchinfo=requests.get(f"{aos_url}/api/systems/{system['system_id']}",headers=headers,verify=False)
        mgmt_ip=switchinfo.json()['facts']['mgmt_ipaddr']
        hostname=switchinfo.json()['status']['hostname']
        vendor=switchinfo.json()['facts']['vendor'].lower()
        vendor_os=switchinfo.json()['facts']['os_family'].lower()
        if system['role'] == 'leaf':
            leafnames.append(hostname)
        if system['role'] == 'spine':
            spinenames.append(hostname)
    # Now add this device to HB
        ds = DeviceSchema(device_id=hostname, host=mgmt_ip,
                  vendor={vendor : {'operating-system': vendor_os}},
                  authentication={"password": {"password": device_password, "username": device_user}})
        hb.device.add(schema=ds)
        print(f"{system['role']} {hostname} has management ip {mgmt_ip}")
  # As long as there is at least one leaf, create a leaf device group for this blueprint
  if len(leafnames) > 0:
      dgs = DeviceGroupSchema(device_group_name=f"{bp_name}-leafs", devices=leafnames)
      dgs.description=f"Leaf switches from AOS blueprint {bp_name}"
      hb.device_group.add(dgs)

  if len(spinenames) > 0:
      dgs = DeviceGroupSchema(device_group_name=f"{bp_name}-spines", devices=spinenames)
      dgs.description=f"Spine switches from AOS blueprint {bp_name}"
      hb.device_group.add(dgs)

grpc_configlet= {
      "ref_archs": [
          "two_stage_l3clos"
      ],
      "generators": [
        {
          "config_style": "junos",
          "section": "system",
          "template_text": "system {\n services {\n   extension-service {\n    request-response {\n     grpc {\n      clear-text;\n     }\n    }\n   }\n  }\n}",
          "negation_template_text": "",
          "filename": ""
        }
      ],
      "display_name": "enableoc"
    }
bp_configlet= {
    "configlet": {
      "generators": [
        {
          "config_style": "junos",
          "section": "system",
          "template_text": "system {\n services {\n   extension-service {\n    request-response {\n     grpc {\n      clear-text;\n     }\n    }\n   }\n  }\n}",
          "negation_template_text": "",
          "filename": ""
        }
      ],
      "display_name": "enableoc"
    },
    "condition": "role in [\"spine\",\"leaf\"]",
    "label": "enableoc"
}
create_oc_configlet=requests.post(f'{aos_url}/api/design/configlets',headers=headers,json=grpc_configlet,verify=False)
apply_oc_configlet=requests.post(f'{aos_url}/api/blueprints/{bpid}/configlets',headers=headers,json=bp_configlet,verify=False)
pprint(apply_oc_configlet.json())
