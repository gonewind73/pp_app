# coding=utf-8 
'''
Created on 2018年1月13日

@author: heguofeng
'''

import os
from _stat import S_ISDIR, S_ISREG
import datetime
import hashlib
import struct
import unittest
import logging
from pp_network import set_debug
import math
import time

NODE_TYPE_FILE = 1
NODE_TYPE_FOLDER = 2
NODE_TYPE_UP = 3
NODE_TYPE_DOWN = 4
NODE_TYPE_IMAGE = {NODE_TYPE_FILE:"image/file.gif", NODE_TYPE_FOLDER:"image/folder.gif"}
NODE_TYPE_STRING = {NODE_TYPE_FILE:"File", NODE_TYPE_FOLDER:"Folder"}
DATE_FILTER = {"All":(0, 10000), "in 1 week":(0, 7), 'in 1 month':(7, 30), "in 3 month":(30, 90), 'in 1 year':(90, 365), '1 year earlier':(365, 10000)}
DATE_FILTER_TUPLE = ("All", "in 1 week", 'in 1 month', "in 3 month", 'in 1 year', '1 year earlier')
SIZE_FILTER = {"All":(0, 100000000000), "< 1 KB":(0, 1000), '<1 MB':(1000, 1000000), "<10 MB":(1000000, 10000000), '>10 MB':(10000000, 100000000000)}
SIZE_FILTER_TUPLE = ("All", "< 1 KB", '<1 MB', "<10 MB", '>10 MB')
FILE_STATUS={"unknown":128,"new":1,"old":2,"same":4}


class FileInfo(object):
    '''
    FileInfo:
        property:
            path
            name
            size
            mtime
            md5
        method:
            load
            hash
    '''

    def __init__(self, filepath, filename="", fileinfo=None,bin_info = None):
        '''
        Constructor
        '''
        self.path = filepath

        if bin_info:
            self.load_info(bin_info)
            return
        self.name = filename
        if fileinfo == None:
            self._load_stat()
        else:
            self._set_stat(fileinfo)
        self.md5 = ""

    def __str__(self):
        return "FileInfo:%s %s size=%d mtime=%d" % (self.path, self.name, self.size, self.mtime)
    
    def _set_stat(self, stat_result):
        if stat_result != None:
            if S_ISREG(stat_result.st_mode):
                self.size = stat_result.st_size
                self.mtime = int(stat_result.st_mtime)
            else:
                raise Exception("Not a regular file!")
       
    def _load_stat(self):
        fullpath = os.path.join(self.path, self.name)
        stat = os.stat(fullpath)
        self._set_stat(stat)

    def get_md5(self):
        maxbuf = 8192
        md5obj = hashlib.md5()
        try: # skip some imreadable file
            with open(os.path.join(self.path,self.name), 'rb') as f:
                while True:
                    buf = f.read(maxbuf)
                    if not buf:
                        f.close()
                        break
                    md5obj.update(buf)
        except:
            return b""
        self.md5 = md5obj.digest()
        return self.md5
    
    def compare(self, other_file_info):
        '''
        if same return 0
        if old return -1
        if new return 1
        '''
        FILE_STATUS_UNKNOWN = 128
        FILE_STATUS_NEW = 1
        FILE_STATUS_OLD = 2 
        FILE_STATUS_SAME = 4
        
        if other_file_info == None:
            return FILE_STATUS_NEW
        if isinstance(other_file_info, FileInfo) == False:
            raise Exception("FileInfo can't compare to other type!")
        if self.name != other_file_info.name :
            raise Exception("File name is not same! maybe not same file")
        if self.mtime > other_file_info.mtime:
            return FILE_STATUS_NEW
        if self.mtime < other_file_info.mtime:
            return FILE_STATUS_OLD
        if self.mtime == other_file_info.mtime:
            if self.size == other_file_info.size:
                return FILE_STATUS_SAME
            else:
                return FILE_STATUS_UNKNOWN
            
    def isSame(self,other_file_info):
        '''
        if same return True
        else False
        '''
        if other_file_info == None:
            return False
        if not isinstance(other_file_info, FileInfo):
            return False
        if (self.name == other_file_info.name
             and self.mtime == other_file_info.mtime 
             and self.size == other_file_info.size):
            return True
        else:
            return False
     
    def remove(self):
        fullPath = os.path.join(self.path, self.name)
        os.remove(fullPath)  # remove the file

    def dump_info(self):
        '''
        dump to bindata
        flag     1byte    1 for file 2 for folder
        length   2byte
        name_len 2byte    len of filename
        name     nbytes    name   (n+3)/4*4
        size     4bytes
        mtime    4bytes
        md5      16bytes
        '''
        
        name_len = len(self.name.encode()) 

        bindata = struct.pack("H%dsII16s"%name_len,
                             name_len,
                             self.name.encode(),
                             self.size,
                             self.mtime,
                             self.get_md5(),
                             )
        length = len(bindata)
        bindata = struct.pack("BI%ds"%len(bindata),
                              1,len(bindata),
                              bindata)
#         logging.debug("fileinfo dump namelen %d binlen %d bindatlen %d"%(name_len,length,len(bindata)))        
        return bindata
    
    def load_info(self,bindata):
        flag,length,name_len = struct.unpack("BIH", bindata[:10])
#         logging.debug("fileinfo load %d namelen %d length %d "%(flag,name_len,length))
        if not flag == 1:
            raise Exception("Error in data")
#         result = struct.unpack("%dsII16s"%name_len,bindata[6:6+length])

        self.name = struct.unpack("%ds"%name_len,bindata[10:10+name_len])[0].decode()
        pos = math.ceil((10+name_len)/4)*4
        result = struct.unpack("II16s",bindata[pos:pos+24])
        self.size = result[0]
        self.mtime = result[1]
        self.md5 =  result[2]
        
#         result = struct.unpack("II16s",bindata[5+name_len:5+24+name_len])
#         self.name = result[0].decode()
#         self.size = result[1]
#         self.mtime = result[2]
#         self.md5 =  result[3]

        return self
    
class FolderInfo(object):
    '''
    folder_info = FolderInfo(folder_path, folder_name="",bin_info=None)
          if bin_info<10 will create a empty folder_info
    
    FolderInfo:
        property:
            path
            name
        method:
            load
            hash
    '''

    def __init__(self, folder_path, folder_name="",bin_info=None):
        '''
        Constructor
        '''
        self.nodes = {}
        if bin_info:
            self.path = folder_path
            self.name = folder_name
            self.load_info(bin_info)
            return
        self.load(folder_path, folder_name)
        
    def load(self, folder_path, folder_name=""):
        self.path = os.path.join(folder_path, folder_name)
        self.name = folder_name
        '''get files in path
           if folder then creat FileFolder
        '''
        full_path = self.path
        if full_path == "":     #create a empty folderInfo,you can use add nodeinfo 
            return 
        for f in os.listdir(full_path):
            f_full_path = os.path.join(full_path, f)
            try:
                stat_result = os.stat(f_full_path)
                if S_ISREG(stat_result.st_mode):
                    self.nodes[f_full_path] = FileInfo(full_path, f, stat_result)
                if S_ISDIR(stat_result.st_mode):
                    self.nodes[f_full_path] = FolderInfo(full_path, f)
            except:
                pass
            
    def __str__(self):
        result = "FolderInfo:%s %s %d nodes\n    " % (self.path, self.name,len(self.nodes))
        for node in self.nodes:
            result += self.nodes[node].__str__()+"\n    "
        return result
        
    def add(self, folder_path, folder_name, node):
        self.path = folder_path
        self.name = folder_name
        self.nodes[os.path.join(node.path, node.name)] = node

    def add_node(self, node):
        if node.path.startswith(self.path):
            self.nodes[os.path.join(node.path, node.name)] = node        

    def compare(self, other_folder_info):
        '''
        return {fullpathfilename:status,
                fullpathfoldername:{ filename:status,
                            ..
                            }
                ...
                }
        '''
        compareResult = {}
        for n in self.nodes:
            node = self.nodes[n]
            otherNode = other_folder_info.nodes.get(n, None) if other_folder_info != None else None
            if isinstance(node, FileInfo):
                otherNode = otherNode if isinstance(otherNode, FileInfo) else None
                compareResult[n] = node.compare(otherNode)
            elif isinstance(node, FolderInfo):
                compareResult[n] = node.compare(otherNode)
        return compareResult
    
    def compare2(self, other_folder_info):
        '''
        return {filename:status,
                foldername:{ filename:status,
                            ..
                            }
                ...
                }
        '''
        compareResult = {}
        for n in self.nodes:
            node = self.nodes[n]
            otherNode = other_folder_info.nodes.get(n, None) if other_folder_info != None else None
            if isinstance(node, FileInfo):
                otherNode = otherNode if isinstance(otherNode, FileInfo) else None
                compareResult[node.name] = node.compare(otherNode)
            elif isinstance(node, FolderInfo):
                compareResult[node.name] = node.compare2(otherNode)
        return compareResult
    
    def getFresh(self,old_folder_info):
        fresh_folder_info = FolderInfo(self.path,self.name,bin_info=b"empty")
        for n in self.nodes:
            node = self.nodes[n]
            otherNode = old_folder_info.nodes.get(n, None) if old_folder_info != None else None
            if isinstance(node, FileInfo):
                otherNode = otherNode if isinstance(otherNode, FileInfo) else None
                if node.compare(otherNode)==FILE_STATUS["new"]: 
                    fresh_folder_info.nodes[node.name] = node
            elif isinstance(node, FolderInfo):
                fresh_node = node.getFresh(otherNode)
                if fresh_node:
                    fresh_folder_info.nodes[node.name] = fresh_node
        if fresh_folder_info.nodes:
            return fresh_folder_info
        else:
            return None
    
    def isIn(self,other_folder_info):
        if not isinstance(other_folder_info, FolderInfo):
            return False
        for n in self.nodes:
            node = self.nodes[n]
            otherNode = other_folder_info.nodes.get(n, None) 
            if not otherNode:
                return False 
            if not node.isSame(otherNode):
                return False
        return  True    
    
    def isSame(self,other_folder_info):
        return self.isIn(other_folder_info) and other_folder_info.isIn(self)
        
        
    def filter(self,filter_func=None):
        '''
        filter_func(node):
            
        '''
        if not filter_func:
            return self
        filted_folder_info=FolderInfo(folder_path=self.path,folder_name=self.name,bin_info=b"empty")
        
        for n in self.nodes:
            node = self.nodes[n]
            if isinstance(node, FolderInfo):
                filted_folder_node = node.filter(filter_func)
                if len(filted_folder_node.nodes):
                    filted_folder_info.add_node(filted_folder_node)
            if isinstance(node, FileInfo):
                if filter_func(node):
                    filted_folder_info.add_node(node)

        return filted_folder_info

        
    def remove(self):
        for f in self.nodes:
            self.nodes[f].remove()
        os.rmdir(os.path.join(self.path, self.name))  # remove the path
        
    def _count(self, folderinfo):
        filecount = 0
        dircount = 0
        filesize = 0
        for node in folderinfo.nodes:
            nodeinfo = folderinfo.nodes[node]
            if isinstance(nodeinfo, FileInfo):
                filecount += 1
                filesize += nodeinfo.size
            if isinstance(nodeinfo, FolderInfo):
                (dc, fc, fs) = self._count(nodeinfo)
                filecount += fc
                filesize += fs
                dircount += dc + 1
        return (dircount, filecount, filesize)
        
    def count(self):
        return self._count(self)
    
    def dump_info(self):
        '''
        dump to bindata
        flag     1byte    1 for file 2 for folder
        length   2bytss
        name_len 1byte    len of filename
        name     nbytes    name
        nodecount 4bytes    node count (file or subfolder)
        node1bindata
        node2bindata
        
        
        '''
        name_len = len(self.name.encode()) 
        nodecount = len(self.nodes)
        bindata = b""
        for node in self.nodes:
            bindata += self.nodes[node].dump_info()
        node_info_len = len(bindata)

        bindata = struct.pack("H%dsI%ds"%(name_len,node_info_len),
                             name_len,
                             self.name.encode(),
                             nodecount,
                             bindata
                             )
        length = len(bindata)
        bindata = struct.pack("BI%ds"%length,
                              2,length,
                              bindata)
        logging.debug("folderinfo dump length %d bindata len %d"%(length,len(bindata)))

        return bindata
    
    def load_info(self,bindata):
        if len(bindata)<10:
            return self
        flag,length,name_len = struct.unpack("BIH", bindata[:10])
        if not flag == 2:
            raise Exception("Error in data")
        result = struct.unpack("%ds"%name_len,bindata[10:10+name_len])
        self.name = result[0].decode()
        pos = math.ceil((10+name_len)/4)*4
        node_count = struct.unpack("I",bindata[pos:4+pos])[0]
#         node_count = result[1]
        pos += 4
        self.path = os.path.join(self.path,self.name)
        logging.debug("folderinfo load node_count %d length %d name_len %d"%(node_count,length,name_len))
        for i in range(node_count):
            flag,length = struct.unpack("BI", bindata[pos:pos+8])
            if flag==1:
                fileinfo = FileInfo(self.path,bin_info=bindata[pos:pos+length+8])
                f_full_path = os.path.join(self.path, fileinfo.name)
                self.nodes[f_full_path] = fileinfo
                pos += length+8
            if flag == 2:
                folderinfo = FolderInfo(self.path,bin_info=bindata[pos:pos+length+8])
                f_full_path = os.path.join(self.path, folderinfo.name)
                self.nodes[f_full_path]=folderinfo
                pos +=  length+8
        return self
        
        


           
class Test(unittest.TestCase):


    def setUp(self):
        set_debug(logging.INFO,"")
        
        pass        


    def tearDown(self):

        pass


#     def testFileInfo(self):
#         f=open("test.txt","wt")
#         f.write("it is a test file")
#         f.close()
#         fileinfo = FileInfo(filepath=".", filename="test.txt", fileinfo=None)
#         print(fileinfo)
#         bindata = fileinfo.dump_info()
#         print(bindata)
#         fileinfo1 = FileInfo(filepath=".",bin_info = bindata)
#         print(fileinfo1) 
#         
#     def testFolderInfo(self):
#  
#         folderinfo = FolderInfo(folder_path=r"C:\Users\heguofeng\workspace\FileManage", folder_name="image")
#         print(folderinfo)
#         bindata = folderinfo.dump_info()
#         print(len(bindata),bindata)
#         folderinfo1 = FolderInfo(folder_path=".",bin_info = bindata)
#         print(folderinfo1)     
    
        
    def testFilter(self):
        folderinfo = FolderInfo(folder_path=r"C:\Users\heguofeng\workspace\FileManage", folder_name="image")
        print(folderinfo)
        filted_info = folderinfo.filter(filter_func=lambda node:True if node.name.startswith("f") else False)
        print(filted_info)
        print(filted_info.dump_info())
        

        
