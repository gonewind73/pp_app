# coding=utf-8 
'''
Created on 2018年4月10日

@author: heguofeng
'''
from pp_control import PPStation
from pp_flow import   Flow
import logging
from pp_link import set_debug
import yaml
import time
from pp_vpn import PPVPN
import optparse
from pp_storage import PPStorage


class PPAppStation(PPStation):
    def __init__(self,config):
        super().__init__(config) 
#         self.flow = Flow(station=self,config=config.get("flow",{}))
#         self.services.update({"flow":self.flow})
        
        if "services" in self.config:
            service_config = self.config["services"]
#             if "proxy" in service_config:
#                 if "proxy_node" in self.config:
#                     self.proxy = PPProxy(self,config.get("proxy_node"),
#                                          data_port=config.get("data_port",7070),
#                                          proxy_port=config.get("proxy_port",443),)
#                     self.services.update({"proxy":self.proxy})
#             if "shell" in service_config or "file" in service_config:
#                 self.file_sheller = FileShellerWithAuth(self)
#                 self.services.update({"file_shell":self.file_sheller})
            if "storage" in service_config:
                storage_config = self.config.get("storage",{})
                self.storage = PPStorage(station = self,
                                 root = storage_config.get("storage_root",r"ppstorage"),
                                 storage_net= storage_config.get("storage_net","public"),
                                 nodes=storage_config.get("nodes",)) 
                self.services.update({"storage":self.storage})           
#                 
    def run_command(self, command_string):
        cmd = command_string.split(" ")
        run = False
        for service in self.services:
            run= True if self.services[service].run_command(command_string) else run
        run= True if super().run_command(command_string) else run
        if not run:
            print("not support command!")        
                 
#         PPStation.run_command(self, command_string)

def main(config):

    print("PPAppStation is lanching...")
    station = PPAppStation(config=config)
    station.start()
    try_count = 0
    while not station.status:
        time.sleep(2)
        station.status = station._check_status()
        try_count += 1
        if try_count > 10 or station.quitting:
            break
    print("node_id=%d online=%s" % (station.node_id, station.status))

    node_type = config.get("node_type","server")
    is_client = node_type == "client"
    while not is_client and not station.quitting:
        time.sleep(3)
        
    s= ""
    while not station.quitting:
        try:
            station.run_command(s)
            print("\n%d>"%station.node_id,end="")
        except Exception as exp:
            logging.exception("error in do command!")
        finally:
            pass
        if not station.quitting:
            s=input()

    print("PPAppStation Quit!")    
    
def create_config(config_file):
    config = {
              "services": {"storage": "enable", },         
              "vpn": { "VlanId" : 0,"VlanSecret" : "12345678", },
              }
    yaml.dump(config,open(config_file,"w"))    
        

def run():
    parser = optparse.OptionParser()
    parser.add_option('--config', default="ppnetwork.yaml", dest='config_file', help='set config file,default is ppnetwork.yaml')
    parser.add_option('--create', default="no", dest='create', help='create config file  ppnetwork.yaml')
    opt, args = parser.parse_args()
    if not opt.create == "no" : 
        create_config(opt.config_file)
    if not (opt.config_file):
        parser.print_help()
    else:
        config = yaml.load(open(opt.config_file))
        config["config_file"] = opt.config_file
        set_debug(config.get("DebugLevel", logging.WARNING),
                    config.get("DebugFile", ""),
                    debug_filter=lambda record: record.filename =="pp_file3.py" or record.filename =="pp_storage3.py" or record.levelno>logging.DEBUG,
                )
        main(config=config)

if __name__ == "__main__":
    run()
    