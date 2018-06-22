#!/usr/bin/env python
#-*- encoding:utf-8 -*-

import redis
import re
import subprocess
from time import sleep
from os.path import join,isfile,isdir
from os import geteuid,path
import sys
import codecs
sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

TextColorRed='\x1b[31m'
TextColorGreen='\x1b[32m'
TextColorWhite='\x1b[0m'


def checkRootPrivilege():
###  检查脚本的当前运行用户是否是 ROOT ###
  RootUID=subprocess.Popen(['id','-u','root'],stdout=subprocess.PIPE).communicate()[0]
  RootUID=RootUID.strip()
  CurrentUID=geteuid()
  return str(RootUID)==str(CurrentUID)


def flushRedisDB(host,port,password='',database=1):
    #### 清空redis 缓存####
    print ('清理redis db:'+str(database))
    try:
        TmpRedisObj=redis.StrictRedis(host=host,port=port,password=password,db=database,socket_connect_timeout=2)
        TmpRedisObj.flushdb()
        return True
    except Exception as e:
        print (TextColorRed+str(e)+TextColorWhite)
        return False


class restartHYServer:
    def __init__(self):
        self.MasterNodeIP=None
        self.MasterNodePort=None
        self.MasterNodePassword=None

        self.Dict4Arguments={'IIPPath':None,
                             'IGIPath':None,
                             'IGSPath':None,
                             'IPMPath':None,
                             'RedisNodes':'',
                             'RedisPassword':'',
                             }

    def __parseConfig(self):
        try:
            with codecs.open(r'config.ini',encoding='utf-8',mode='r') as f:
                TmpFileContent=f.read()
            TmpArguemntsList=re.findall(r'^\s*(\w+)\s*=\s*(.*?)\n',TmpFileContent,
                                        flags=re.MULTILINE|re.DOTALL)
            for key,value in TmpArguemntsList:
                self.Dict4Arguments[key]=value

        except Exception as e:
            print (str(e))

        ### 验证参数有效性 ####
        for item in ['IIPPath','IGIPath','IGSPath','IPMPath']:
           if (self.Dict4Arguments[item] is  None) or len(self.Dict4Arguments[item].strip())==0:
               self.Dict4Arguments[item]=None

        TmpList=re.findall(r'\s*\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}\s*',self.Dict4Arguments['RedisNodes'])
        TmpList=[x.strip() for x in TmpList]
        self.Dict4Arguments['RedisNodes']=TmpList




    def detectMasterNode(self):
        for item in self.Dict4Arguments['RedisNodes']:
            TmpHost,TmpPort=item.split(':')

            #### Round one:try to connect without password  ##
            try:
                TmpRedisObj=redis.StrictRedis(host=TmpHost,port=TmpPort,socket_timeout=2)
                TmpInfoDict=TmpRedisObj.info()

                if 'role' in TmpInfoDict:
                    self.MasterNodeIP=TmpHost
                    self.MasterNodePort=TmpPort
                    self.MasterNodePassword=''
                elif 'master0' in TmpInfoDict:
                    TmpString=TmpInfoDict['master0']['address']
                    self.MasterNodeIP,self.MasterNodePort=TmpString.split(':')
                    self.MasterNodePassword=self.Dict4Arguments['RedisPassword']
                break
            except:
                pass

            #### Round two: try to connect with passsword ###
            try:
                TmpRedisObj=redis.StrictRedis(host=TmpHost,port=TmpPort,password=self.Dict4Arguments['RedisPassword'],socket_timeout=2)
                TmpInfoDict=TmpRedisObj.info()

                if 'role' in TmpInfoDict:
                    self.MasterNodeIP=TmpHost
                    self.MasterNodePort=TmpPort
                    self.MasterNodePassword=self.Dict4Arguments['RedisPassword']
                elif 'master0' in TmpInfoDict:
                    TmpString=TmpInfoDict['master0']['address']
                    self.MasterNodeIP,self.MasterNodePort=TmpString.split(':')
                    self.MasterNodePassword=self.Dict4Arguments['RedisPassword']
                break
            except:
                pass
        if self.MasterNodeIP and self.MasterNodePort:
            print (TextColorGreen+'检测到Master 节点IP：'+str(self.MasterNodeIP)+TextColorWhite)
            print (TextColorGreen+'检测到Master节点端口：'+str(self.MasterNodePort)+TextColorWhite)
            print (TextColorGreen+"Master节点密码："+str(self.MasterNodePassword)+TextColorWhite)
        else:
            print (TextColorRed+"无法正确识别Redis Master节点"+TextColorWhite)


    def restartIIP(self):
        if not self.Dict4Arguments['IIPPath']:
            print (TextColorRed+'错误：未配置IIP 安装路径，无法重启IIP进程')
            return 1
        TmpResult=subprocess.Popen("jps |grep -v 'Jps'|awk '{print $1}'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
        TmpPIDList=re.findall(r'\d+',TmpResult)

        for pid in TmpPIDList:
            try:
                with open(r'/proc/%s/cmdline'%(pid,),mode='r') as f:
                    TmpFileContent=f.read()
                if self.Dict4Arguments['IIPPath'] in TmpFileContent:
                    print (TextColorGreen+'检测到IIP 进程PID：'+str(pid)+' 正在停止进程...'+TextColorWhite)
                    subprocess.call('kill -9 %s'%(pid,),shell=True)
            except Exception as e:
                continue
        sleep(1)

        while True:
            Choice4FlushDB=raw_input('是否需要清空Redis 缓存(yes/no):')
            Choice4FlushDB=Choice4FlushDB.strip().lower()

            if Choice4FlushDB=='yes':
                print ('即将清理 Redis缓存....')
                isSucceed=flushRedisDB(host=self.MasterNodeIP,port=self.MasterNodePort,password=self.MasterNodePassword,
                             database=1)
                if not isSucceed:
                    print (TextColorRed+'错误：清空Redis 缓存失败，无法继续重启，,请手动启动进程！'+TextColorWhite)
                    return 1
                else:
                    print (TextColorGreen+'成功清理Redis缓存'+TextColorWhite)
                    break
            elif Choice4FlushDB=='no':
                print ('跳过对redis缓存的清理')
                break

        TmpExecPath=join(self.Dict4Arguments['IIPPath'],'bin/startup.sh')
        if not isfile(TmpExecPath):
            print (TextColorRed+'错误：无法找到启动文件：'+'重启失败，请手动启动IIP'+TextColorWhite)
            return 1
        subprocess.call('sh '+TmpExecPath,shell=True)
        print ('采编IIP 已经重启完毕，请检查相关日志')


    def restartIGI(self):
        if not self.Dict4Arguments['IGIPath']:
            print (TextColorRed+'错误：未配置IGI 安装路径，无法重启IGI进程')
            return 1
        TmpResult=subprocess.Popen("jps |grep -v 'Jps'|awk '{print $1}'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
        TmpPIDList=re.findall(r'\d+',TmpResult)

        for pid in TmpPIDList:
            try:
                with open(r'/proc/%s/cmdline'%(pid,),mode='r') as f:
                    TmpFileContent=f.read()
                if self.Dict4Arguments['IGIPath'] in TmpFileContent:
                    print (TextColorGreen+'检测到IGI 进程PID：'+str(pid)+' 正在停止进程...'+TextColorWhite)
                    subprocess.call('kill -9 %s'%(pid,),shell=True)
            except Exception as e:
                continue
        sleep(1)

        while True:
            Choice4FlushDB=raw_input('是否需要清空Redis 缓存(yes/no):')
            Choice4FlushDB=Choice4FlushDB.strip().lower()
###            Choice4FlushDB='no'    ### 问政互动目前暂不支持清理缓存   #####

            if Choice4FlushDB=='yes':
                print ('即将清理 Redis缓存....')
                isSucceed=flushRedisDB(host=self.MasterNodeIP,port=self.MasterNodePort,password=self.MasterNodePassword,
                             database=7)
                if not isSucceed:
                    print (TextColorRed+'错误：清空Redis 缓存失败，无法继续重启，,请手动启动进程！'+TextColorWhite)
                    return 1
                else:
                    print (TextColorGreen+'成功清理Redis缓存'+TextColorWhite)
                    break
            elif Choice4FlushDB=='no':
                print ('跳过对redis缓存的清理')
                break

        TmpExecPath=join(self.Dict4Arguments['IGIPath'],'bin/startup.sh')
        if not isfile(TmpExecPath):
            print (TextColorRed+'错误：无法找到启动文件：'+'重启失败，请手动启动IGI'+TextColorWhite)
            return 1
        subprocess.call('sh '+TmpExecPath,shell=True)
        print ('问政互动IGI 已经重启完毕，请检查相关日志')



    def restartIGS(self):
        if not self.Dict4Arguments['IGSPath']:
            print (TextColorRed+'错误：未配置IGS 安装路径，无法重启IGS进程')
            return 1
        TmpResult=subprocess.Popen("jps |grep -v 'Jps'|awk '{print $1}'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
        TmpPIDList=re.findall(r'\d+',TmpResult)

        for pid in TmpPIDList:
            try:
                with open(r'/proc/%s/cmdline'%(pid,),mode='r') as f:
                    TmpFileContent=f.read()
                if self.Dict4Arguments['IGSPath'] in TmpFileContent:
                    print (TextColorGreen+'检测到IGS 进程PID：'+str(pid)+' 正在停止进程...'+TextColorWhite)
                    subprocess.call('kill -9 %s'%(pid,),shell=True)
            except Exception as e:
                continue
        sleep(1)

        while True:
            Choice4FlushDB=raw_input('是否需要清空Redis 缓存(yes/no):')
            Choice4FlushDB=Choice4FlushDB.strip().lower()
            Choice4FlushDB='no'    ### 检索IGS目前暂不支持清理缓存   #####

            if Choice4FlushDB=='yes':
                print ('即将清理 Redis缓存....')
                isSucceed=flushRedisDB(host=self.MasterNodeIP,port=self.MasterNodePort,password=self.MasterNodePassword,
                             database=10)
                if not isSucceed:
                    print (TextColorRed+'错误：清空Redis 缓存失败，无法继续重启，,请手动启动进程！'+TextColorWhite)
                    return 1
                else:
                    print (TextColorGreen+'成功清理Redis缓存'+TextColorWhite)
                    break
            elif Choice4FlushDB=='no':
                print ('跳过对redis缓存的清理')
                break

        TmpExecPath=join(self.Dict4Arguments['IGSPath'],'bin/startup.sh')
        if not isfile(TmpExecPath):
            print (TextColorRed+'错误：无法找到启动文件：'+'重启失败，请手动启动IGS'+TextColorWhite)
            return 1
        subprocess.call('sh '+TmpExecPath,shell=True)
        print ('智能检索IGS 已经重启完毕，请检查相关日志')


    def restartIPM(self):
        if not self.Dict4Arguments['IPMPath']:
            print (TextColorRed+'错误：未配置IPM 安装路径，无法重启IPM进程')
            return 1
        TmpResult=subprocess.Popen("jps |grep -v 'Jps'|awk '{print $1}'",shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).communicate()[0]
        TmpPIDList=re.findall(r'\d+',TmpResult)

        for pid in TmpPIDList:
            try:
                with open(r'/proc/%s/cmdline'%(pid,),mode='r') as f:
                    TmpFileContent=f.read()
                if self.Dict4Arguments['IPMPath'] in TmpFileContent:
                    print (TextColorGreen+'检测到IPM 进程PID：'+str(pid)+' 正在停止进程...'+TextColorWhite)
                    subprocess.call('kill -9 %s'%(pid,),shell=True)
            except Exception as e:
                continue
        sleep(1)

        while True:
            Choice4FlushDB=raw_input('是否需要清空Redis 缓存(yes/no):')
            Choice4FlushDB=Choice4FlushDB.strip().lower()

            if Choice4FlushDB=='yes':
                print ('即将清理 Redis缓存....')
                isSucceed=flushRedisDB(host=self.MasterNodeIP,port=self.MasterNodePort,password=self.MasterNodePassword,
                             database=10)
                if not isSucceed:
                    print (TextColorRed+'错误：清空Redis 缓存失败，无法继续重启,请手动启动进程！'+TextColorWhite)
                    return 1
                else:
                    print (TextColorGreen+'成功清理Redis缓存'+TextColorWhite)
                    break
            elif Choice4FlushDB=='no':
                print ('跳过对redis缓存的清理')
                break

        TmpExecPath=join(self.Dict4Arguments['IPMPath'],'startup.sh')
        if not isfile(TmpExecPath):
            print (TextColorRed+'错误：无法找到启动文件：'+'重启失败，请手动启动IPM'+TextColorWhite)
            return 1
        subprocess.Popen('sh '+TmpExecPath+' &',shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        print ('绩效考核IPM 已经重启完毕，请检查相关日志')


    def __preStart(self):
        if not checkRootPrivilege():
            print (TextColorRed+'错误：运行本工具需要root账号，请切换至root并重试，程序退出.'+TextColorWhite)
            exit(1)

        self.__parseConfig()
        if not self.Dict4Arguments['RedisNodes']:
            print (TextColorRed+'错误：配置文件中未配置redis节点信息，或配置信息有误，程序退出'+TextColorWhite)
            exit(1)

        self.detectMasterNode()
        if not self.MasterNodeIP:
            print (TextColorRed+'错误：无法识别Redis  主节点，程序退出.'+TextColorWhite)
            exit(1)

    def runMenu(self):
        self.__preStart()
        while True:
            print (TextColorGreen+'#########  欢迎使用“海云系统”，本工具将帮助你完成服务的重启。  ######')
            print ('           1、重启 IIP;')
            print ('           2、重启 IGS;')
            print ('           3、重启 IGI;')
            print ('           4、重启 IPM;')
            print ('           0、退出;'+TextColorWhite)

            choice=raw_input('请输入数值序号:')
            choice=choice.strip()

            if choice=='1':
                if (not self.Dict4Arguments['IIPPath']) or (not path.exists(self.Dict4Arguments['IIPPath'])) :
                    print (TextColorRed+'IIP 配置路径有误，无法重启'+TextColorWhite)
                    continue
                self.restartIIP()
            if choice=='2':
                if (not self.Dict4Arguments['IGSPath']) or (not path.exists(self.Dict4Arguments['IGSPath'])) :
                    print (TextColorRed+'IGS 配置路径有误，无法重启'+TextColorWhite)
                    continue
                self.restartIGS()
            if choice=='3':
                if (not self.Dict4Arguments['IGIPath']) or (not path.exists(self.Dict4Arguments['IGIPath'])) :
                    print (TextColorRed+'IGI 配置路径有误，无法重启'+TextColorWhite)
                    continue
                self.restartIGI()
            if choice=='4':
                if (not self.Dict4Arguments['IPMPath']) or (not path.exists(self.Dict4Arguments['IPMPath'])) :
                    print (TextColorRed+'IPM 配置路径有误，无法重启'+TextColorWhite)
                    continue
                self.restartIPM()
            if choice=='0':
                exit(0)


tmp=restartHYServer()
tmp.runMenu()