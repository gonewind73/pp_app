# coding=utf-8 
'''
Created on 2018年3月21日

@author: heguofeng
'''
import unittest
from pp_file import  Filer

import logging
import shutil
import os

import time
import struct
import threading
from _thread import start_new_thread
from pp_link import  NAT_TYPE, PP_APPID, BroadCastId
from pp_control import PPNetApp, PPStation
from filefolder import FolderInfo, FileInfo, FILE_STATUS
from pseudo_net import FakeNet
from logtool import set_debug
 
class PPStorage(PPNetApp):
    '''
    node  save the data block,and will automatic sync to 2 other node
    
    /ppstorage/
    XXXXX 或  XXXXX.blk 
    blk 是索引文件    ，主要节省空间
        version  fullpath  start  size    
        .在下载  文件时，将blk文件保存为 XXXX文件。
    XXXXX 是 数据文件
    blks version  file_size,file_md5,create,modify, blockscount XXXXmd5  start  size  XXXXmd5  start size 
    
    will sync auto in same content network  
    
    config need:
    storage_root: 
    
    /ppstorage/
    XXXXX 或  XXXXX.blk 
    blk 是索引文件    ，主要节省空间
        version  fullpath  start  size    
        .在下载  文件时，将blk文件保存为 XXXX文件。
    XXXXX 是 数据文件
    blks version  file_size,file_md5,create,modify, blockscount XXXXmd5  start  size  XXXXmd5  start size 
    
    will sync auto in same content network  
    '''
    class StorageMessage(PPNetApp.AppMessage):
        '''
        parameters = {
                "text":"test",}
        tm = TextMessage(dictdata={"command":"echo",
                                   "parameters":parameters} )
        bindata = tm.dump()
        tm1 = FileMessage(bindata=bindata)
        app_id = tm1.get("app_id")
        text = tm1.get("parameters")["text"]
        
        src_id   dst_id   app_id  sequence applen  appdata
        4byte    4byte    2byte   4byte   2byte   applen
        
        Storage
        appid       appdata
        30          [cmd,paralen,tag,len,value,tag len value ...]
                     1    1     TLV
        cmd(parameters):
            0x01 node_req   len  src_id  
            0x02 node_res   len  node_id
            0x03 content_req   len  content
            0x04 contetn_res   len  node_id
        parameters(type,struct_type):
            0x10 content  (byte,s)   filename
            0x11 location  (int, I)  node_id  
    '''                
        def __init__(self, **kwargs):
            tags_id = {
              "node_req":1,"node_res":2,"content_req":3,"content_res":4,"content_del": 0x05,
              "content":0x10,"location":0x11,"net_token":0x16,"content_list":0x13, "content_items":0x14,          
              }
            parameter_type = {0x10:"str",0x11:"I"}
            super().__init__(app_id=PP_APPID["Storage"],
                             tags_id=tags_id,
                             parameter_type=parameter_type,
                             **kwargs)
    
        
    def __init__(self,station,root,storage_net,nodes):
        self.station =  station
        self.root = root
        self.storage_net = storage_net  # 1 for client 2 for node 3 both
        self.nodes = nodes     # node of storage {node_id:private}
        self.contents =  {}  # node of has content {content_id:[node1,node2...]}

        if not os.path.exists(self.root):
            os.mkdir(self.root)
        self.filer = Filer(self.station,work_dir=self.root)            
        self.storage_info_timer=None
        self.station.set_app_process(PP_APPID["Storage"],self.process)

        pass
    
    def start(self):

        self.find_node()
        start_new_thread(self.sync_check,())
        
    def sync_check(self):
        logging.debug("%d timer to check sync!"%self.station.node_id)
        self.find_node()
        self.storage_info()
        self.sync_delete()
        time.sleep(1)
        for node in self.nodes.keys():
            if node in self.station.peers and self.station.peers[node].status:
                self.compare_storage_info(node)
        
        if not self.station.quitting:
            self.storage_info_timer = threading.Timer(600,self.sync_check)
            self.storage_info_timer.start()
    
    def sync_delete(self):
        delete_info_path = os.path.join(self.root,"storage.info.dlt")
        if os.path.exists(delete_info_path):
            with open(delete_info_path,"rb") as info_file:
                delete_folder_info = FolderInfo(folder_path=self.root,bin_info=info_file.read())
                self.delete_folder(delete_folder_info, "")
            logging.info("success sync delete folder! %s"%delete_folder_info)
            os.remove(delete_info_path)
        pass
    
    def delete_folder(self,folder_node,path):
        for node_id in folder_node.nodes:
            node = folder_node.nodes[node_id]
            if isinstance(node, FileInfo):
                self.delete_content(os.path.join(path,node.name))
                logging.info("success sync delete file! %s"%os.path.join(path,node.name))
            if isinstance(node, FolderInfo):
                self.delete_folder(node,path = os.path.join(path,node.name))
    
    def storage_info(self,refresh=False):
        '''
        refresh = True will ignore delete file 
                  False  if somedelete will crate storage.info.dlt
        generate storage.info
        timer check up to date
        and compare to other nodes storage.info , 
            if newer download the storage.info.node ,and compare 
            download new file 
        '''
        info_path = os.path.join(self.root,"storage.info")
        folder_info = FolderInfo(folder_path=self.root).filter(filter_func=lambda node:
                                            True 
                                            if not node.name.startswith("storage.info") 
                                            else False )

        if os.path.exists(info_path) and os.path.getsize(info_path):
#             storage_info = FileInfo(filepath=self.root,filename="storage.info")
#             later = folder_info.filter(filter_func=lambda node:
#                                             True 
#                                             if node.mtime>storage_info.mtime 
#                                             else False )
#             if not len(later.nodes):
#                 return
            with open(info_path,"rb") as info_file:
                last_folder_info = FolderInfo(folder_path=self.root,bin_info=info_file.read())
#             print(folder_info,last_folder_info,last_folder_info.isSame(folder_info))
            if last_folder_info.isSame(folder_info):
                return
            deleted = last_folder_info.getFresh(folder_info)
            if deleted and not refresh:
    #             print(deleted)
                with open(os.path.join(self.root,"storage.info.dlt"),"wb") as f:
                    f.write(deleted.dump_info())            
        with open(info_path,"wb") as f:
            f.write(folder_info.dump_info())
        logging.info("%d new storage.info generate!"%self.station.node_id)

        pass
    
    
    def get_storage_info(self,peer_id,file_info=None):
        '''
        get other node's storage_info
        then call compare
        file_info is an filemessage's parameters

        '''
        remote_info_name = "storage.info"
        local_info_name = "storage.info."+str(peer_id)

        logging.debug("%d start get %d storage info!"%(self.station.node_id,peer_id))
        local_info_fullpath = os.path.join(self.root,local_info_name)
            
        if os.path.exists(local_info_fullpath) and os.path.getsize(local_info_fullpath):
            local_storage_info = FileInfo(filepath=self.root,filename=local_info_name)
#             print(local_storage_info.mtime,os.path.getmtime(local_info_fullpath))
            if file_info:
                logging.info("%d receive fileinfo %s %d %d"%(self.station.node_id,
                                                             file_info,
                                                             file_info["file_date"],
                                                             local_storage_info.mtime))
                if file_info["file_date"] > local_storage_info.mtime:
                    self.filer.get_file(peer_id, remote_info_name, local_info_name, self.after_get_storage_info)
                else:
                    self.compare_storage_info(peer_id,fresh=True)
            else:
                self.filer.get_file_info(peer_id,remote_info_name,self.get_storage_info)
        else:
            self.filer.get_file(peer_id, remote_info_name, local_info_name, self.after_get_storage_info)

        pass
    
    def after_get_storage_info(self,action,peer_id,action_content,error_code,error_message):
        if error_code==0:
            logging.info("%d  success get storage_info:%s"%(self.station.node_id,error_message))
            self.compare_storage_info(peer_id,fresh=True)
        else:
            logging.warning("%d error in get storage_info:%s"%(self.station.node_id,error_message))
    
    def compare_storage_info(self,peer_id, fresh = False):
        '''

        and compare to other nodes storage.info , 
            if newer download the storage.info.node ,and compare 
            download new file 
        '''
        peer_info_name = "storage.info."+str(peer_id)
        self_info_name = "storage.info"
        peer_info_fullpath = os.path.join(self.root,peer_info_name)
        self_info_fullpath = os.path.join(self.root,self_info_name)     
        if not fresh:
            self.get_storage_info(peer_id, file_info=None)
            return
        
        if not os.path.exists(self_info_fullpath):
            self.storage_info()
        if os.path.exists(peer_info_fullpath):
            with open(peer_info_fullpath,"rb") as peer_file,open(self_info_fullpath,"rb") as self_file:
                peer_bin = peer_file.read()
                self_bin = self_file.read()
#                 print(peer_bin,self_bin)
                if not peer_bin:
                    logging.warning("didn't receive the peer storage info.")
                    return
                peer_storage_info = FolderInfo(self.root,bin_info=peer_bin)
                self_storage_info = FolderInfo(self.root,bin_info=self_bin)
                logging.debug("peers:\n%s \nself:\n%s"%(peer_storage_info,self_storage_info))
            compare_result = peer_storage_info.compare2(self_storage_info)
            logging.debug("compare result:%s"%compare_result)
            self.sync_files(peer_id,"",compare_result)
        else:
            self.get_storage_info(peer_id, file_info=None)
        pass
    
    def sync_files(self,peer_id,path,files):
        '''
        compare_result = 
                {filename:status,
                foldername:{ filename:status,
                            ..
                            }
                ...
                }
        '''

        for name in files:
            if isinstance(files[name], int):
                remote = os.path.join(path,name)
                local = os.path.join(path,name)
#                 if files[name]==FILE_STATUS["new"]:
#                     self.filer.put_file(peer_id, local, remote, callback=None)
                if files[name]==FILE_STATUS["new"]:
                    self.filer.get_file(peer_id, remote, local, callback=self.check_file)
            if isinstance(files[name],dict):
                self.sync_files(peer_id,path+name, files[name])
                
    def check_file(self,action,peer_id,action_content,error_code,error_message):
        if error_code==0:
            return
        else:
            fullpath = os.path.join(self.root,action_content)
            if os.path.exists(fullpath):
                os.remove(fullpath)
            if os.path.exists(action_content+",pbuf"):
                os.remove(action_content+",pbuf")
            return
                
    
    def list_content(self,path=""):
        logging.debug(self.root)
        if path:
            return os.listdir(os.path.join(self.root,path))
        else:
            return os.listdir(self.root)
        
    def found(self,content):
        if content in self.list_content():
            return True
        else:
            return False
        
    def get(self,filename,localname):
        if self.found(filename):
            return shutil.copy(filename,localname)
        else:
            self.contents[filename] = []
            self.find_content(filename)
        return
    
    def download(self,peer_id,content,localname): 
        self.filer.get_file(peer_id=peer_id, remote = content, local=localname)
        pass
    
    def put(self,localname,remotename=""):
        for peer_id in self.nodes.keys(): 
            self.filer.connect(peer_id = peer_id)
            self.filer.put_file(peer_id=peer_id, remote = remotename, local=localname)
        pass
    
    def delete(self,filename):
        fullpath = os.path.join(self.root,filename)
        if os.path.exists(fullpath):
            os.unlink(fullpath)
        else:
            logging.warning("try to delete %s is not exist!"%fullpath)
        self.storage_info(refresh=True)
        pass
    
    def find_node(self):
        '''
        send node_req to network
        waiting for node_res
        '''

        logging.debug("%d start find node."%self.station.node_id)
        self.station.send_msg(BroadCastId,
                      self.StorageMessage(dictdata={"command":"node_req",
                                               "parameters":{"location":self.station.node_id}}),
                      need_ack=False)
        pass
    
    def node_response(self,peer_id):
        '''
        send node_res to network
        '''

        logging.debug("%d response node_req for %d."%(self.station.node_id,peer_id))
        self.station.send_msg(peer_id,
                      self.StorageMessage(dictdata={"command":"node_res",
                                               "parameters":{"location":self.station.node_id}}),
                      need_ack=False)   
        
    def find_content(self,content):
        '''
        send node_req to network
        waiting for node_res
        '''

        logging.debug("%d start find content."%self.station.node_id)
        self.station.send_msg(BroadCastId,
                      self.StorageMessage(dictdata={"command":"content_req",
                                               "parameters":{"content":content,
                                                             "location":self.station.node_id}}),
                      need_ack=True)
        pass
    
    
    def content_response(self,content,peer_id): 
        '''
        send node_res to network
        '''

        logging.debug("%d response node_req for %d."%(self.station.node_id,peer_id))
        self.station.send_msg(peer_id,
                      self.StorageMessage(dictdata={"command":"content_res",
                                               "parameters":{"content":content,
                                                             "location":self.station.node_id}}),
                      need_ack=True)    
        
    def delete_content(self,content):
        '''
        send node_req to network
        waiting for node_res
        '''

        logging.debug("%d start find content."%self.station.node_id)
        self.station.send_msg(BroadCastId,
                      self.StorageMessage(dictdata={"command":"content_del",
                                               "parameters":{"content":content}}),
                      need_ack=True)
        pass                        
        
    def process(self,ppmsg,addr):

        message = self.StorageMessage(bindata=ppmsg.get("app_data"))
        command =  message.get("command")
        parameters = message.get("parameters")
        logging.info("%d receive storage message command %s with %s"%(self.station.node_id,command,parameters))
        if command == "node_req":
            storage_net = parameters["storage_net"] if "storage_net" in parameters else "public"
            logging.debug("%d node_req storage_net %s"%(self.station.node_id,self.storage_net))
            if self.storage_net ==  storage_net:
                self.node_response(parameters["location"])
        if command == "node_res":
            self.nodes[parameters["location"]]="2"
        if command == "content_req":
            if self.found(parameters["content"]):
                self.content_response(content =  parameters["content"],
                                      peer_id =  parameters["location"])
        if command == "content_res":
            self.get_content(peer_id = parameters["location"],
                             content = parameters["content"])
        if command == "content_del":
            self.delete(filename= parameters["content"]) 
        return           
    
    def get_content(self,peer_id,content):
        if content not in self.contents:
            self.contents[content] =[]
        
        self.contents[content].append(peer_id)
        
        pass
    
    def quit(self):
        self.station.set_app_process(PP_APPID["Storage"],None)
        if self.storage_info_timer:
            self.storage_info_timer.cancel()
            
    def run_command(self, command_string):
        cmd = command_string.split(" ")
        if cmd[0] in ["list","node","sync","delete"]:
            if cmd[0]=="list":
                print(self.list_content(),self.nodes)
            elif cmd[0]=="node":
                self.find_node()
                time.sleep(3)
                print(self.nodes)
            elif cmd[0]=="sync":
                self.sync_check()
            elif cmd[0]=="delete" and len(cmd)>=2:
                self.delete_content(content = cmd[1])
            elif cmd[0] =="get" and len(cmd)>=3:
                self.get_file(remote = cmd[1],local = cmd[2])
            elif cmd[0] =="put" and len(cmd)>=3:
                self.put_file(local = cmd[1],remote = cmd[2])        
            return True
        return False


    

class Test(unittest.TestCase):


    def setUp(self):
        set_debug(logging.INFO,"")
#         self.stationA = FakeAppNet(100)
#         self.stationB = FakeAppNet(201)   
#         self.file_shellerA = FileSheller(self.stationA)             
#         self.file_shellerB = FileSheller(self.stationB)    
#         processes = {100:self.stationA.process_msg,
#                      201:self.stationB.process_msg}
#         self.stationA.set_process(processes)
#         self.stationB.set_process(processes)     
                
        self.fake_net = FakeNet()
        self.stationA = self.fake_net.fake(PPStation(config={"node_id":100,"ip":"0.0.0.0","node_port":54330,"db_file":"nodesA.pkl",
                                                             "node_ip":"180.153.152.193", "nat_type":NAT_TYPE["Turnable"]}))
 
        self.stationA.beat_interval=1
        self.stationA.start()
  
        self.stationB = self.fake_net.fake(PPStation(config={"node_id":201,"ip":"0.0.0.0","node_port":54330,"db_file":"nodesB.pkl",
                                                             "node_ip":"116.153.152.193", "nat_type":NAT_TYPE["Turnable"]}))
        self.stationB.beat_interval=1
        self.stationB.start()  
                
        self.storageA = PPStorage(station=self.stationA,root=r"C:\Users\heguofeng\workspace\FileManage\ppstorage",
                                  storage_net="home",nodes={100:"home",201:"home"})
        self.storageB = PPStorage(station=self.stationB,root=r"C:\Users\heguofeng\workspace\FileManage\ppstorage1",
                                  storage_net="home",nodes={100:"home",201:"home"})    
#         self.storageA.start()
#         self.storageB.start()      
        
        pass        

    def emptydir(self,root):
        filelist=os.listdir(root)
        for f in filelist:
            os.remove(os.path.join(root, f ))
            

    def tearDown(self):

        pass


#     def testlist(self):
#         print(self.storageA.list_content())
#         print(self.storageB.list_content())
#         pass
    
#     def testfind(self):
#         self.storageB.find_node()
#         time.sleep(1)
#         print(self.storageB.nodes)
#         self.storageB.find_content("test3.txt")
#         time.sleep(1)
#         print(self.storageB.contents)
         
#     def testdelete(self):
#         self.storageB.find_node()
#         time.sleep(1)
#         print(self.storageB.nodes)
#         self.storageB.delete_content("test3.txt")
#         time.sleep(1)
#         print(self.storageB.contents)
        
    def testSync(self):
        self.emptydir(self.storageA.root)
        self.emptydir(self.storageB.root)
        with open(os.path.join(self.storageA.root,"test.txt"),"wt") as f:
            f.write("storage test\n"*10)
        time.sleep(2)
        self.storageA.start()
        self.storageB.start()
        time.sleep(80)
        self.assertTrue(os.path.exists(os.path.join(self.storageB.root,"test.txt")), "sync file")
