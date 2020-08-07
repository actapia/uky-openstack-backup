import argparse
import os
import progressbar
import re
import random
import string
import sys
import yaml
import novaclient.client
import glanceclient
from getpass import getpass
from IPython import embed
from keystoneauth1 import loading
from keystoneauth1 import session
from time import sleep
from urlparse import urlparse

def replace_netloc(parse_result,hostname=None,port=None):
    if hostname is None:
        hostname  = parse_result.hostname
    if port is None:
        port = parse_result.port
    return parse_result._replace(netloc="{}:{}".format(hostname,port))
    
def search_servers(servers,**kwargs):
    return servers.list(search_opts=kwargs)
    
def choices(alphabet,k):
    result = []
    for j in range(k):
        result.append(random.choice(alphabet))
    return result
    
def gen_uuid(length=8):
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(choices(alphabet,length))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-u","--username")
    parser.add_argument("-p","--project-id")
    parser.add_argument("-a","--auth-url")
    parser.add_argument("-C","--config",default=os.path.expanduser("~/.config/openstack/clouds.yaml"))
    parser.add_argument("-w","--pw-prompt",action="store_true")
    parser.add_argument("name",help="instance name")
    parser.add_argument("-W","--wait",action="store_true",help="wait for backup image to be created")
    parser.add_argument("-d","--download",const=True,nargs="?",action="store",default=False)
    args = parser.parse_args()
    if args.pw_prompt:
        password = getpass()
    if not (args.username and args.project_id and args.auth_url and args.pw_prompt):
        # Try to load config from clouds.yaml.
        with open(args.config,"r") as clouds:
            clouds_yaml = yaml.safe_load(clouds)
            if not args.username:
                args.username = clouds_yaml["clouds"]["openstack"]["auth"]["username"]
            if not args.project_id:
                args.project_id = clouds_yaml["clouds"]["openstack"]["auth"]["project_id"]
            if not args.auth_url:
                args.auth_url = clouds_yaml["clouds"]["openstack"]["auth"]["auth_url"]
            if not args.pw_prompt:
                password = clouds_yaml["clouds"]["openstack"]["auth"]["password"]
    credentials = {"auth_url": args.auth_url,
                   "username": args.username,
                   "password": password,
                   "project_id": args.project_id,
                   "user_domain_name": "Default"}
    print("Running with arguments {}".format(credentials))
    print(args.download)
    # Connect to OpenStack API.
    loader = loading.get_plugin_loader("password")
    auth = loader.load_from_options(**credentials)
    nova_sess = session.Session(auth=auth)
    nova = novaclient.client.Client(2.1,session=nova_sess)
    glance_sess = session.Session(auth=auth)
    glance = glanceclient.Client(2,session=glance_sess)
    # Override endpoints.
    openstack_url = urlparse(args.auth_url).hostname
    glance_default_endpoint = urlparse(glance.images.http_client.get_endpoint())
    glance.images.http_client.endpoint_override = replace_netloc(glance_default_endpoint,hostname=openstack_url).geturl()
    nova_default_endpoint = urlparse(nova.servers.api.client.get_endpoint())
    nova.servers.client.endpoint_override = replace_netloc(nova_default_endpoint,hostname=openstack_url).geturl()
    # Backup the specified instance.
    servers = search_servers(nova.servers,name="^{}$".format(re.escape(args.name)))
    if len(servers) > 1:
        print("Ambiguous name {}!".format(args.name))
        sys.exit(1)
    if not servers:
        print("No servers found matching name {}.".format(args.name))
        sys.exit(1)
    server = servers[0]
    image_names = {i["name"] for i in glance.images.list()}
    image_name = "backup-{}".format(gen_uuid())
    print("generating image name")
    while image_name in image_names:
        image_name = "backup-{}".format(gen_uuid())
    if args.download is True:
        args.download = "{}.qcow2".format(image_name)
    print("backin' up")
    server.backup(image_name,"uky-openstack-backup",1)
    image_id = None
    print("getting id")
    while not image_id:
        try:
            image_id = next(i for i in glance.images.list() if i["name"] == image_name)["id"]
        except StopIteration:
            sleep(5)
    status = glance.images.get(image_id)["status"]
    if args.download or args.wait:
        while status != "active":
            sleep(5)
            status = glance.images.get(image_id)["status"]
    if args.download:
        with open(args.download,"wb") as image_file:
            blocks = glance.images.data(image_id)
            downloaded = 0
            with progressbar.ProgressBar(max_value=len(blocks)) as bar:
                for block in blocks:
                    image_file.write(block)
                    downloaded = downloaded + len(block)
                    bar.update(downloaded)
