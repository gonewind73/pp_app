 PPAPP

======

PPAPP 是一系列基于ppnetwork 的 网络应用。


安装
=======
pip install python-ppapp

    
配置
=========
配置文件采用yaml格式。文件名称自定义，如ppapp.yaml

示例如下
::
{
#ppnet 
node_id: 818300194,
node_port: 54194,

node_nic: "无线网卡",
DebugLevel: 20,
#DebugFile: 'pplink.log',

node_file: nodes.pkl,
node_type: client,

#flow
flow :  {
flow_port: 9000,
},

#service
"services": {
"vpn": enable,
},         
    
#vpn
vpn: {
VlanId : 0,
IPRange : { start : 192.168.33.1, end : 192.168.33.255 },
VlanIP : 0.0.0.0,
VlanMask : 255.255.255.0,
VlanSecret : "12345678",
}   
} 

运行
=====
ppapp -h | --help   帮助
ppapp  --config  pp.yaml   用指定的配置文件（pp.yaml） 运行。
ppapp     用缺省配置文件ppnetwork.yaml 运行
ppapp --create yes 产生最简配置，运行
 

安全说明
========
1.  任何节点加入虚拟局网接入都需要验证，网络号+密钥 +时间窗口。 
2.  所有虚拟网络中数据传输为透传，没有使用加密。
3.  虚拟网中的地址分配，可以自行指定，也可以动态获得（配置文件中为0.0.0.0）。
      如果自行指定有冲突，后进入者会动态分配另一个空闲地址。可以通过网络命令 如 ifconfig 或 ipconfig 查看
4.  网络号和网络地址段必须保持一致，否则会导致地址分配错误。

## 激励原则
1.   按转发流量、时段、区域（时延） 激励 

