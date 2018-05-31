# coding=utf-8 
'''
Created on 2018年3月22日

@author: heguofeng
'''
import unittest


import struct
import logging
import os
import time
import threading

import sys
from pp_link import PP_APPID,PPMessage
from pp_control import Block, PPConnection
from pseudo_net import FakeAppNet
from logtool import set_debug

FILE_TAG = {
          # command
          "get":5,
          "put":3,
          "data":8,
          "file_info":9,
          "get_info":6,
          
          "open":1,
          "info_req":6,
          "info_res":9,
          "read":5,
          "write":8,
          "close":10,
          # tag
         "file_name":0x20,
         "file_size": 0x21,
         "block_data": 0x22,
         "block_start":0x23,
         "block_end": 0x24,
         "error_info": 0x25,
         "local_file": 0x26,  # for put ,where  to save file
         "block_md5": 0x27,
         "file_date":0x28,
         }

def get_fullpath(work_dir, filename):    
    if sys.platform.startswith("win"):
        fullpath_filename = filename  if filename.find(":") > 0 else os.path.join(work_dir, filename)
    else:
        fullpath_filename = filename  if filename.startswith("/") else os.path.join(work_dir, filename)
#     logging.debug("fullpath:%s"%fullpath_filename)
    return fullpath_filename

class FileMessage(PPMessage):
    '''
    parameters = {
            FILE_TAG["file_name"]:"test.txt",
            FILE_TAG["start"]:0,
            FILE_TAG["end"]:0,}
            
    fm = FileMessage(dictdata={"command":FILE_TAG["read"],
                               "parameters":parameters} )
    bindata = fm.dump()
    fm1 = FileMessage(bindata=bindata)
    
    src_id   dst_id   app_id  sequence applen  appdata
    4byte    4byte    2byte   4byte   2byte   applen
    
    appid:     app        appdata
    0015       file       [cmd,paralen,tag,len,value,tag len value ...]
                            1    1     TLV
    
    cmd(parameters):
        open(filename)
        info_req(filename)  == get_info
        info_res(filename,size,mtime,md5) == file_info
        read(filename,start,end) == get
        write(filename,start,end,data) == data
        close(filename)
        put(local_filename,filename)
    parameters(type,struct_type):
        filename    string     s
        start       int        I
        end         int        I
        size        int        I
        mtime       int        I
        md5         bytes      s
    '''
                
    def __init__(self, **kwargs):
        
        super().__init__(**kwargs)
        self.dict_data["app_id"] = PP_APPID["File"]

    def load(self, bindata):
        self.dict_data["command"], paralen = struct.unpack("BB", bindata[0:2])
        self.dict_data["parameters"] = {}
        start_pos = 2
        while start_pos < len(bindata):
            pos, result = self.load_TLV(bindata[start_pos:])
            self.dict_data["parameters"][result[0]] = result[2]
            start_pos += pos
        return
    
    def dump(self):
        data = struct.pack("BB",
                           self.dict_data["command"], 0
                            )
        for tag in self.dict_data["parameters"]:
            # print(self.dict_data,tag)
            data += self.dump_TLV((tag, len(self.dict_data["parameters"][tag]), self.dict_data["parameters"][tag]))  
        return data


    

class FileBlock(Block):
    def __init__(self, work_dir=".", filename="", mode="rb"):
        self.work_dir = work_dir
        self.size = 0
        self.mtime = 0
        self.file = None
        if filename:
            self.load_file(filename, mode)
        pass
    
    def open(self, mode="rb"):
        self.file = None
        self.fullpath = get_fullpath(self.work_dir, self.block_id)
        logging.debug("fullpath %s" % self.fullpath)
        
        if mode.startswith("r") and os.path.exists(self.fullpath):
            self.size = os.path.getsize(self.fullpath)
            self.file = open(self.fullpath, mode)
            self.mtime = int(os.path.getmtime(self.fullpath))
        elif mode.startswith("w"):
            self.file = open(self.fullpath, mode)
            self.mtime = int(time.time())      
        else:      
            return None       
        self.pos = 0  
        return self
    
    def close(self, mtime=0):
        if self.file:
            self.file.close()
            if mtime:
                os.utime(self.fullpath, (mtime, mtime))
            self.file = None
        return self

    def load_file(self, file_name, mode="rb", start=0, end=0):

        self.block_id = file_name
#         self.open(mode)
        return self
    
    def load_buffer(self):
        '''
        for continue transfer  after failure
        return unreceived blocks dictionay
        {start1:end1,...startn,endn}
        '''
        buffer = {}
        if self.file and os.path.exists(self.block_id + ".pbuf"):
            with open(self.block_id + ".pbuf", "rb") as f:
                file_md5, file_size, received_bytes, block_count = struct.unpack("16sIII", f.read(28))
                for i in range(block_count):
                    block = f.read(8)
                    result = struct.unpack("II", block)
                    buffer[result[0]] = result[1]
            logging.info("buffer loaded!")
            return file_md5, file_size, received_bytes, buffer
        return "", 0, 0, {}
    
    def save_buffer(self, file_md5, file_size, received_bytes, buffer):
        if buffer:
            with open(self.block_id + ".pbuf", "wb") as f:
                f.write(struct.pack("16sIII", file_md5, file_size, received_bytes, len(buffer)))
                for block in buffer:
                    f.write(struct.pack("II", block, buffer[block]))
                print("Buffer saved!")
        else:
            if os.path.exists(self.block_id + ".pbuf"):
                os.remove(self.block_id + ".pbuf")
        return     
    
    def seek(self, start, mode=0):
        '''
        0 from begin
        '''
        self.pos = start
        self.file.seek(start, mode)
        
    def read(self, byte_count):
        self.file.seek(self.pos)
        data = self.file.read(byte_count)
        self.pos += len(data)
        return data
    
    def write(self, bindata):
        self.file.seek(self.pos)
        self.file.write(bindata)
        self.pos += len(bindata)
        self.size = self.size if self.size > self.pos else self.pos
        return 

    def get_md5(self, start=0, end=0):
        if not self.file:
            self.open()
            return super().get_md5()
            self.close()
        else:
            return super().get_md5()
  
class BlockSender(PPConnection):
    '''
    single block sender
    
    bs = BlockSend(station,callback)
    bs.set_blockin(block_in)
    waiting get_info or get message
    info_process
        bs.connect(peer_id)
        bs.send_info()
    block_process 
        bs.connect(peer_id)
        bs.send_block()
        receive get(start = block_size)
            bs.done
                call callback
    
    '''
    def __init__(self, station, peer_id=0, block_in=None, callback=None):
        '''
        '''
        super().__init__(station, callback)
   
        if PP_APPID["File"] not in self.station.process_list:
            self.set_app_process(PP_APPID["File"], self.process)
        
        self.stage = 0
        self.retry_count = 0
        self.sending = False    
        
        self.set_blockin(block_in)
        if peer_id:
            self.connect(peer_id)
    
    def set_blockin(self, block_in=None):
        if block_in:
            self.block_in = block_in.open(mode="rb")
            if self.block_in:
                self.block_size = block_in.size if block_in else 0
                self.stage = 1
                self._timer()
                logging.info("%d waiting to send block %s" % (self.station.node_id, block_in.block_id))
            else:
                self.done(error_code=2,error_message="%d error to open  %s" % (self.station.node_id, block_in.block_id))
        return self
           
    def send_block(self, start, end):
        '''
        start_pos = filesize  finished
        end_pos = 0  ==>filesize
        '''
        if self.stage != 1:
            return self.block_size
        
        if start == self.block_size:
            self.done(error_code=0 , error_message="%d send %s  compelete! block_size %d." % (self.station.node_id, self.block_in.block_id, self.block_size,))
            return self.block_size
        
        realend = end if end else self.block_size
        logging.debug("send file with start = %d  end= %d" % (start, realend))
                
        self.block_in.seek(start, 0)
        self.sending = True
        for i in range(0, int((realend - start + 1023) / 1024)):
            print(">", end="")
            buffer = self.block_in.read(1024)
            fs_msg = FileMessage(dictdata={"command":FILE_TAG["data"],
                                       "parameters":{FILE_TAG["file_name"]:self.block_in.block_id.encode(),
                                                     FILE_TAG["file_size"]:struct.pack("I", self.block_in.size),
                                                     FILE_TAG["block_start"]:struct.pack("I", start + i * 1024),
                                                     FILE_TAG["block_end"]:struct.pack("I", start + i * 1024 + len(buffer)),
                                                     FILE_TAG["block_data"]:buffer}})
            self.send(fs_msg, need_ack=False)
        return realend        
    
    def send_info(self, start=0, end=0):
        '''
        process get_info message
        send block info to peer
        '''
        if not self.stage == 1:
            logging.debug("%d not ready!" % self.station.node_id)
            return
        parameters = {
                        FILE_TAG["file_name"]:self.block_in.block_id.encode(),
                        FILE_TAG["file_size"]:struct.pack("I", self.block_in.size),
                        FILE_TAG["block_md5"]:self.block_in.get_md5(),
                        FILE_TAG["file_date"]:struct.pack("I", self.block_in.mtime)}
        if not (start == 0 and end == 0):
            parameters.update({
                        FILE_TAG["block_start"]:struct.pack("I", start),
                        FILE_TAG["block_end"]:struct.pack("I", end),
                         })
        fs_msg = FileMessage(dictdata={
                                       "command":   FILE_TAG["file_info"],
                                       "parameters":parameters}
                             )
        logging.debug("%d send block info %s" % (self.station.node_id, parameters))
        self.send(fs_msg, need_ack=True)
        if not self.block_in.size:
            self.done(error_code=0, error_message="size 0 file.complete!")
        
    def send_error(self, error_message):
        exp = error_message.encode()
        fs_msg = FileMessage(dictdata={
                                "command":FILE_TAG["file_info"],
                                "parameters":{
                                              FILE_TAG["file_name"]:self.block_in.block_id.encode(),
                                              FILE_TAG["error_info"]:exp,
                                             }})
        self.send(fs_msg, need_ack=False)
        pass
    
    def block_process(self, parameters):
        '''
        process get_block message
        send block data to peer
        '''
        file_name = parameters[FILE_TAG["file_name"]].decode()
        start = struct.unpack("I", parameters[FILE_TAG["block_start"]])[0]
        end = struct.unpack("I", parameters[FILE_TAG["block_end"]])[0]

        if not self.stage == 1:
            self.block_in = FileBlock(filename=file_name)
        
        self.send_block(start=start, end=end)
        
    def info_process(self, parameters):
        file_name = parameters[FILE_TAG["file_name"]].decode()
        if not self.stage == 1:
            self.block_in = FileBlock(filename=file_name)
        self.send_info()        
        
    def process(self, ppmsg, addr):
        
        if not self.connect(ppmsg.get("src_id")):
            return 
        fs_message = FileMessage(bindata=ppmsg.get("app_data"))

        parameters = fs_message.get("parameters")
        logging.debug("%d receive file message %s" % (self.station.node_id, parameters))
                    
        if fs_message.get("command") == FILE_TAG["get"]:
            self.block_process(parameters)
        if fs_message.get("command") == FILE_TAG["get_info"]:
            self.info_process(parameters)

    def done(self, error_code=0, error_message=""):
#         logging.info("%d block send done with code %d %s"%(self.station.node_id,error_code,error_message))
#         print(self.callback)
        if self.stage == 2:
            return 
        if self.block_in:
            self.block_in.close()
        self.stage = 2
        if self.callback:
            content =  self.block_in.block_id if self.block_in else "None"
            self.callback("send", self.peer_id, content, error_code, error_message)
        if self.station.process_list[PP_APPID["File"]] == self.process:
            self.set_app_process(PP_APPID["File"], None)
       
    def put_file(self, local, remote,):
        '''
        file_name : peers remote filename = local filename  , peer will use it to re-get file
        file_local: peers local filename
        '''
        fs_msg = FileMessage(dictdata={"command":FILE_TAG["put"],
                                           "parameters":{
                                                    FILE_TAG["file_name"]:local.encode(),
                                                    FILE_TAG["local_file"]:remote.encode(),
                                                    FILE_TAG["block_start"]:struct.pack("I", 0),
                                                    FILE_TAG["block_end"]:struct.pack("I", 0)}
                                       })
        self.send(fs_msg, need_ack=True)
        logging.debug("%d put file %s to remote %s " % (self.station.node_id, local, remote))
        
    def _timer(self):
        if self.sending:
            self.sending = False
            self.retry_count = 0
        else: 
            self.retry_count += 1
            if self.retry_count < 10 :
                pass
            else:
                self.done(error_code=2, error_message="%s timeout!" % self.block_in.block_id)
                return
        if self.stage == 1:
            threading.Timer(3, self._timer).start()
        pass    

class BlockReceiver(PPConnection):
    '''
    single block receive
    
    br = BlockReceiver(station,callback)
    br.set_blockout(block_out)
    br.get_block(remote_id)
        load_buffer or send get_info to remote
    wait info and data 
        info_process  
            set info and get(start=0)
        data_process  
            write to blockout
            if finish 
                done()
                    send get(start=block_size)
    timer
        get_remain()
        
    '''
    
    def __init__(self, station, peer_id=0, remote_id="", block_out=None, callback=None):
        '''
        '''
        super().__init__(station, callback)
        
        if PP_APPID["File"] not in self.station.process_list:
            self.set_app_process(PP_APPID["File"], self.process)
            
        self.stage = 0
        self.info_callback = None
        self.block_size = 0
        self.block_mtime = int(time.time())
        if peer_id:
            self.connect(peer_id)

        self.set_blockout(block_out)
        self.remote_id = remote_id
        
        if remote_id and block_out:
            self.get_block(remote_id)        

    def set_blockout(self, block_out):
        if block_out:
            self.block_out = block_out.open("wb+")
            if not self.block_out:
                self.done(error_code=2, error_message="open output error!")
#         logging.debug("%s"%self.block_out.file)
        else:
            self.block_out = None
        return self
        
    def get_block(self, remote_id):
#         self.set_blockout(block_out)
        self.remote_id = remote_id
        logging.debug("%d remote %s" % (self.station.node_id, self.remote_id))
        self.starttime = time.time()
        self.receiving = False
        self.stage = 0  # 0 init  1 ready 2 finished 
        self.received_bytes = 0
        self.retry_count = 0
        self.block_size = 0
        self.block_md5 = b''
        if self.block_out:
            self.block_md5, self.block_size, self.received_bytes, self.buffer = self.block_out.load_buffer()
            if not self.buffer:
                self.get_info()
            else:
                self.stage = 1
                self._check() 
        else:
            print("set block out first.")
            return self
        return self
            
    def get_info(self, start=0, end=0, callback=None):
        '''
        return file_size,block md5 with start and end,file_date
        '''
        real_end = end if end else self.block_size
        logging.debug("%d get file_info with start = %d  end= %d" % (self.station.node_id, start, real_end))
        fs_msg = FileMessage(dictdata={"command":FILE_TAG["get_info"],
                                       "parameters":{
                                                    FILE_TAG["file_name"]:self.remote_id.encode(),
                                                    FILE_TAG["block_start"]:struct.pack("I", start),
                                                    FILE_TAG["block_end"]:struct.pack("I", real_end)}
                                       })
        self.send(fs_msg, need_ack=True)  
        if callback:
            self.info_callback = callback  
        return self  
    
    def get_data(self, start=0, end=0):
        '''
        start = -1 get remain
        '''
        if self.stage != 1:
            return

        if self.block_size == 0:
            self.done(error_code=0, error_message="size 0 ,done!")
            return 
        
        real_start = start
        real_end = end
        if end == 0 and self.buffer and real_start in self.buffer:
            real_end = self.buffer[real_start] 
            while real_end in self.buffer:
                real_end = self.buffer[real_end]
            
        logging.debug("get block with realstart = %d  end= %d" % (real_start, real_end))
        fs_msg = FileMessage(dictdata={"command":FILE_TAG["get"],
                                       "parameters":{
                                                    FILE_TAG["file_name"]:self.remote_id.encode(),
                                                    FILE_TAG["block_start"]:struct.pack("I", real_start),
                                                    FILE_TAG["block_end"]:struct.pack("I", real_end)}
                                       })
        self.send(fs_msg, need_ack=False)     
    
    def done(self, error_code=0, error_message=""):

        if self.block_size:
            self.get_data(start=self.block_size, end=self.block_size)
        if self.stage == 2:
            return
        if self.stage == 1:
            self.block_out.save_buffer(self.block_md5, self.block_size, self.received_bytes, self.buffer)
        self.stage = 2
        if not error_code:
            if not self.block_out.get_md5() == self.block_md5:
                error_code = 5
                error_message = "check md5 error!"
        if self.block_out:
            self.block_out.close(mtime=self.block_mtime)
        if self.callback:
            self.callback("receive", self.peer_id, self.remote_id, error_code, error_message)
            
        if self.station.process_list[PP_APPID["File"]] == self.process:
            self.set_app_process(PP_APPID["File"], None)
        
    def set_info(self, parameters):
        '''
        "file_name":0x20,
         "file_size": 0x21,
         "block_data": 0x22,
         "block_start":0x23,
         "block_end": 0x24,
         "error_info": 0x25,
         "local_file": 0x26,
         "block_md5": 0x27,
         "file_date":0x28,
        '''
        logging.debug("%d receive fileinfo = %s" % (self.station.node_id, parameters))
        if FILE_TAG["file_size"] in parameters:
            self.block_size = struct.unpack("I", parameters[FILE_TAG["file_size"]])[0]
        if FILE_TAG["block_md5"] in parameters:
            self.block_md5 = parameters[FILE_TAG["block_md5"]]
        if FILE_TAG["file_date"] in parameters:
            self.block_mtime = struct.unpack("I", parameters[FILE_TAG["file_date"]])[0]           
        if FILE_TAG["error_info"] in parameters:
            print("There are an error:%s" % parameters[FILE_TAG["error_info"]].decode())
            
        if self.info_callback:
            callback = self.info_callback
            self.info_callback = None
            self.done(error_code=5, error_message="get %s info finish."%self.remote_id)
            callback(self.peer_id, parameters)  
            return      
        if self.block_out:
            self.stage = 1
            self._get_buffer(self.block_size)
            self._check()  
        else:
            self.done(error_code=1, error_message="no output!")
        pass
    
    def _get_buffer(self, file_size):
        self.buffer = {}
        for i in range(0, int(file_size / 1024)):
            self.buffer[i * 1024] = i * 1024 + 1024
        if (file_size % 1024):
            self.buffer[int(file_size / 1024) * 1024] = file_size
        return self.buffer
    
    def receive(self, block_size, start, end, block_data):

        if self.stage != 1:
            return 
        print("<", end="")
        logging.debug("block_size %d received %d start %d end %d" % (block_size, self.received_bytes, start, end,))

        data_len = len(block_data)
        if start in self.buffer and data_len == self.buffer[start] - start :
            self.block_out.seek(start, 0)
            self.block_out.write(block_data)
            del self.buffer[start]
            self.received_bytes += data_len
            self.receiving = True
        if len(self.buffer) == 0  :
            self.done(error_code=0, error_message="download %s finish!"%self.remote_id)
            return block_size
        else:
            return 0
        
    def get_remain(self):
        if self.buffer:
            buffer_list = list(self.buffer.keys())
            
            while buffer_list:
                tempstart = min(buffer_list)
                tempend = self.buffer[tempstart]
                buffer_list.remove(tempstart)
                while tempend in buffer_list:
                    buffer_list.remove(tempend)
                    tempend = self.buffer[tempend]
#                 print("\nsend start %d end %d remain%d"%(tempstart,tempend,len(buffer_list)))
                self.get_data(start=tempstart, end=tempend)
            else :
                return
        else:
            self.done(error_code=0, error_message="download complete!") 
            
    def info_process(self, parameters):
        '''
        process info message
        prepare to get block 
        '''
        logging.debug("%d parameters %s" % (self.station.node_id, parameters))
        filename = parameters[FILE_TAG["file_name"]].decode()
        if filename == self.remote_id:
            self.set_info(parameters)        
        pass
    
    def block_process(self, parameters):
        '''
        process block message
        receive block data from peer
        '''
        block_id = parameters[FILE_TAG["file_name"]].decode()
        if FILE_TAG["error_info"] in parameters:
            print("Error remote %s" % parameters[FILE_TAG["error_info"]].decode())
            if block_id == self.block_id:
                self.done(error_code=1, error_message=parameters[FILE_TAG["error_info"]].decode())
            return
        block_size = struct.unpack("I", parameters[FILE_TAG["file_size"]])[0]
        start = struct.unpack("I", parameters[FILE_TAG["block_start"]])[0]
        end = struct.unpack("I", parameters[FILE_TAG["block_end"]])[0]
        block_data = parameters[FILE_TAG["block_data"]] 
        if block_id == self.remote_id:
            size = self.receive(block_size, start, end, block_data)
        if size or not block_size:
            self.done(error_code=0, error_message="download complete!")
            
    def process(self, ppmsg, addr):
        fs_message = FileMessage(bindata=ppmsg.get("app_data"))
        peer_id = ppmsg.get("src_id")
        parameters = fs_message.get("parameters")
        logging.debug("%d receive %d file message %s" % (self.station.node_id, peer_id, parameters))
        
        if fs_message.get("command") == FILE_TAG["file_info"]:
            self.info_process(parameters)            
        if fs_message.get("command") == FILE_TAG["data"]:
            self.block_process(parameters)
        if fs_message.get("command") == FILE_TAG["put"]:
            self.connect(peer_id=peer_id)
            local = parameters[FILE_TAG["local_file"]].decode()
            remote = parameters[FILE_TAG["file_name"]].decode()
            self.set_blockout(Block())
            self.get_block(remote_id=remote)
    
    def timer(self):
        '''
        check not received
        '''
        pass
                
    def _check(self):
        if not self.stage == 1:
            return
        
        if self.receiving:
            self.receiving = False
            self.retry_count = 0
        else: 
            self.retry_count += 1
            if self.retry_count < 10 :
                self.get_remain()
            else:
                self.done(error_code=2, error_message="get %s failure!" % self.remote_id)
                return
        if self.stage == 1:
            threading.Timer(1, self._check).start()
        pass    

class FileSender(BlockSender):
    pass

class FileReceiver(BlockReceiver):
    def __init__(self, station, peer_id=0, remote_id="", block_out=None, callback=None):
        super().__init__(station, peer_id, remote_id, block_out, callback)
        
    def process(self, ppmsg, addr):
        fs_message = FileMessage(bindata=ppmsg.get("app_data"))
        peer_id = ppmsg.get("src_id")
        parameters = fs_message.get("parameters")
        logging.debug("%d receive %d file message %s" % (self.station.node_id, peer_id, parameters))
        
        if fs_message.get("command") == FILE_TAG["file_info"]:
            self.info_process(parameters)            
        if fs_message.get("command") == FILE_TAG["data"]:
            self.block_process(parameters)
        if fs_message.get("command") == FILE_TAG["put"]:
            self.connect(peer_id=peer_id)
            local = parameters[FILE_TAG["local_file"]].decode()
            remote = parameters[FILE_TAG["file_name"]].decode()
            self.set_blockout(FileBlock(filename=local, mode="wb+"))
            self.get_block(remote_id=remote)
                            
class Filer(object):
    '''
    filer = Filer(station)
    filer.get_file(peer_id,remote,local,callback)
        if finish will save remote to local,and call callback
    filer.put_file(peer_id,local,remote,callback)
        if finish will put local to remote ,and call callback  
    file.set_work_dir(work_dir)  
        if you dont like fullpath of local
        remote depend on its programer, fullpath is ok       

    callback(action,peer_id,action_content,error_code,error_message)
    '''
    def __init__(self, station, work_dir="."):
        self.station = station
        self.send_queue = {}  # key={(peer_id,localfilename):[FileSender,callback]
        self.receive_queue = {}  # key={(peer_id,remotefilename):[FileReceive,callback]
        self.station.set_app_process(PP_APPID["File"], self.file_process)
        self.work_dir = work_dir
        self.waiting = {}

        pass
    
    def quit(self):
        self.station.set_app_process(PP_APPID["File"], None)
        
    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
             
    def get_file(self, peer_id, remote, local, callback=None):
        logging.info("%d start get file %s from %d will save in %s." % (self.station.node_id, remote, peer_id, local))
        receiver = self.get_receiver(peer_id, remote, callback)
        out = FileBlock(filename=local, mode="wb+", work_dir=self.work_dir)
        receiver.set_blockout(block_out=out)
        receiver.get_block(remote)
    
    def get_file_info(self, peer_id, remote, callback):
        '''
        callback(peer_id,remote,fileinfo)
        '''
        receiver = self.get_receiver(peer_id, remote, callback=None)
        receiver.get_info(callback=callback)
        
        pass

    def put_file(self, peer_id, local, remote, callback=None):
        sender = self.get_sender(peer_id, local, callback)
        sender.put_file(local, remote)

    def get_sender(self, peer_id, file_name, callback=None):
        if (peer_id, file_name) not in self.send_queue:
            self.send_queue[(peer_id, file_name)] = [FileSender(station=self.station,
                                                              peer_id=peer_id,
                                                              block_in=FileBlock(work_dir=self.work_dir).load_file(file_name),
                                                              callback=self.finish),
                                                    callback]
        return self.send_queue[(peer_id, file_name)][0]

    def get_receiver(self, peer_id, remote, callback=None):
        if (peer_id, remote) not in self.receive_queue:
            self.receive_queue[(peer_id, remote)] = [FileReceiver(station=self.station,
                                                                peer_id=peer_id,
                                                                remote_id=remote,
                                                                callback=self.finish),
                                                    callback]
        return self.receive_queue[(peer_id, remote)][0]
        
    def file_process(self, ppmsg, addr):
        fs_message = FileMessage(bindata=ppmsg.get("app_data"))
        peer_id = ppmsg.get("src_id")
        parameters = fs_message.get("parameters")
        file_name = parameters[FILE_TAG["file_name"]].decode()
        if not fs_message.get("command") == FILE_TAG["data"]:
            logging.debug("%d receive %d file message %s filename %s" % (self.station.node_id, peer_id, parameters, file_name))
        
#         logging.debug("%d filename %s comand %d"%(peer_id,file_name,fs_message.get("command")))
        if fs_message.get("command") == FILE_TAG["get"]:
            self.get_sender(peer_id, file_name).block_process(parameters)
        if fs_message.get("command") == FILE_TAG["get_info"]:
            logging.debug(self.send_queue)
            self.get_sender(peer_id, file_name).info_process(parameters)
        if fs_message.get("command") == FILE_TAG["file_info"]:
            self.get_receiver(peer_id, file_name).info_process(parameters)            
        if fs_message.get("command") == FILE_TAG["data"]:
            self.get_receiver(peer_id, file_name).block_process(parameters)
        if fs_message.get("command") == FILE_TAG["put"]:
            self.get_file(peer_id=peer_id,
                          local=parameters[FILE_TAG["local_file"]].decode(),
                          remote=parameters[FILE_TAG["file_name"]].decode())
                
    def finish(self, action, peer_id, action_content="", error_code=0, error_message=""):
        if action not in ("connect","disconnect"):
            logging.info("%s with %d done. return %d with message: %s " % (action, peer_id, error_code, error_message))
        if action == "send":
            if (peer_id, action_content) in self.send_queue:
                callback = self.send_queue[(peer_id, action_content)][1]
                del self.send_queue[(peer_id, action_content)]
                if callback:
                    callback(action,peer_id, action_content, error_code, error_message)
                
        if action == "receive":
            if (peer_id, action_content) in self.receive_queue:
                callback = self.receive_queue[(peer_id, action_content)][1]
                del self.receive_queue[(peer_id, action_content)]       
                if callback:
                    callback(action,peer_id, action_content, error_code, error_message)
                    
class Test(unittest.TestCase):

    def setUp(self):
        set_debug(logging.INFO, "")
        self.stationA = FakeAppNet(node_id=100)
        self.stationB = FakeAppNet(node_id=200)

    def blocksetup(self):
        pass
    
    def filersetup(self):
        self.filerA = Filer(self.stationA)
        self.filerB = Filer(self.stationB)
        processes = {100:self.filerA.file_process,
                     200:self.filerB.file_process}
        self.stationA.set_process(processes)
        self.stationB.set_process(processes)    
        try:
            os.remove("test.txt")
            os.remove("test1.txt")
            os.remove("test2.txt") 
            os.remove("test3.txt")
            os.remove("test4.txt")
            os.remove("test4.txt.pbuf")
        except:
            pass           
        pass

    def tearDown(self):
        pass

    def show(self, action, peer_id, action_content="", error_code=0, error_message=""):
        print("%d load callback success!" % peer_id)
        pass
    
    def testBlockSend(self):
        self.BlockA = BlockSender(self.stationA)
        self.BlockB = BlockReceiver(self.stationB)
      
        processes = {100:self.BlockA.process,
                     200:self.BlockB.process}
        self.stationA.set_process(processes)
        self.stationB.set_process(processes)   
        blockin = Block(block_id="test", buffer=b"it is my station!")
        blockout = Block()
        self.BlockA.connect(peer_id=200).set_blockin(blockin).set_callback(callback=self.show)
        self.BlockB.connect(peer_id=100).set_blockout(blockout).set_callback(callback=self.show)
        self.BlockB.get_block("test")
        self.assertEqual(blockin.get_md5(), blockout.get_md5(), "blocksend and receiver")
 
        print(blockout.buffer, blockout.block_id)
         
    def testFiler_getSize0(self):
        self.filersetup()
        f = open("test.txt", "wt")
        f.close()
        self.filerA.get_file(200, "test.txt", "test1.txt")
        self.assertTrue(os.path.exists("test1.txt"), "test1 size 0 file download")
          
    def testFiler_get(self):       
        self.filersetup() 
        with open("test.txt", "wt") as f:
            f.write("ppfile test\n"*100)
        self.filerA.get_file(200, "test.txt", "test2.txt")
        self.assertTrue(os.path.exists("test2.txt"), "test2 file download")
        self.assertEqual(FileBlock(filename="test2.txt").get_md5(), FileBlock(filename="test.txt").get_md5(), "test2 file download and md5")
          
    def testFile_put(self):
        self.filersetup()
        with open("test.txt", "wt") as f:
            f.write("ppfile test\n"*100)
        self.filerA.put_file(200, "test.txt", "test3.txt")
        self.assertTrue(os.path.exists("test3.txt"), "test3 file upload")
        pass

    def pause(self):
        self.stationA.status = False
        logging.info("pause A")
        print("pause A") 
        
#     def testFile_buffer(self):
#         self.filersetup()
#         with open("test.txt","wt") as f:
#             f.write("ppfile test\n"*1000000)
# 
#         threading.Timer(1,self.pause).start()
#         self.filerA.get_file(200,"test.txt","test4.txt")
#         time.sleep(60)
#         self.assertTrue(os.path.exists("test4.txt.pbuf"), "test4 file buffer")        
#  
#         self.stationA.status=True
#         self.filerA.get_file(200,"test.txt","test4.txt")               
#         
#         self.assertTrue(os.path.exists("test4.txt"), "test3 file upload")        
#         self.assertFalse(os.path.exists("test4.txt.pbuf"), "test4 file buffer")        

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
