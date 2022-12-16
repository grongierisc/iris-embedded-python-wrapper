from importlib.abc import MetaPathFinder
from importlib.abc import Loader
import importlib
from types import ModuleType
import math
import marshal
import sys
import iris

sources=iris.gref("^ROUTINE")
binaries=iris.gref("^rPYC")
MAX_STRING_SIZE=3800000

def getFromDirectory(directory, path):
	level=len(path)
	if level == 1:
		return directory[path[0]]
	elif level == 2:
		return directory[path[0],path[1]]
	elif level == 3:
		return directory[path[0],path[1],path[2]]
	elif level == 4:
		return directory[path[0],path[1],path[2],path[3]]
	elif level == 5:
		return directory[path[0],path[1],path[2],path[3],path[4]]	
	elif level == 6:
		return directory[path[0],path[1],path[2],path[3],path[4],path[5]]	
	elif level == 7:
		return directory[path[0],path[1],path[2],path[3],path[4],path[5],path[6]]	
	elif level == 8:
		return directory[path[0],path[1],path[2],path[3],path[4],path[5],path[6],path[7]]	
	elif level == 9:
		return directory[path[0],path[1],path[2],path[3],path[4],path[5],path[6],path[7],path[8]]	

#name is name of rtn with .py
def getSourceCode(name):
	currentP = [name] + [0,0]
	length = getFromDirectory(sources, currentP)
	currentP.pop()
	if not length or length == 0:
		return None
	code = ""
	for i in range(1,int(length)+1):
		currentP.append(i)
		code += getFromDirectory(sources, currentP)
		code += "\r\n"
		currentP.pop()
	return code

def getCodeFromBinary(name):
	length = binaries.get([name],0)
	if (length < 1):
		return None
	codeBytes = binaries.getAsBytes([name,1])
	for i in range(1,int(length)):
		codeBytes += binaries.getAsBytes([name,i+1])
	return marshal.loads(codeBytes)

# def checkCode(directory, path):
# 	currentP = [p for p in path] + [0,0]
# 	length = getFromDirectory(directory, currentP)
# 	currentP.pop()
# 	if not length or length == 0:
# 		return None
# 	return length

def checkCode(name):
	#code exist for module

	if binaries.get([name],0) > 0:
		return True
	sub = binaries.order([name+"."])
	#there exists some subpackage
	if (sub and sub[:len(name)] == name):
		return True
	return False

def compileCode(name):
	path = name.split(".")
	classname = path[-1]
	code = getSourceCode(name+".py")
	if code:
		codeobj = compile(code,classname,"exec")
		compiledpython = marshal.dumps(codeobj)

		#store in database
		length=len(compiledpython)
		chunks = math.ceil(length / MAX_STRING_SIZE)
		binaries[name] = chunks
		for i in range(chunks):
			binaries[name,i+1] = compiledpython[i*MAX_STRING_SIZE:min(MAX_STRING_SIZE*(i+1),length)]

		#delete old version of this module 
		# if name in sys.modules:
		# 	del sys.modules[name]
		return 1
	return 0

#
# Impedence matcher prototype
#

def mapping_GetAt(self,key):
	return self[key]

def mapping_SetAt(self,value,key):
	self[key] = value

def sequence_GetAt(self,index):
	return self[index-1]

def sequence_SetAt(self,value,index):
	self[index-1] = value

def materialize(obj):
	if isinstance(obj,collections.abc.Mapping):
		obj.Count = obj.__len__
		obj.GetAt = mapping_GetAt
		obj.SetAt = mapping_SetAt
		return True
	if isinstance(obj,collections.abc.Sequence):
		obj.Count = obj.__len__
		obj.GetAt = sequence_GetAt
		obj.SetAt = sequence_SetAt
		return True
	return False

class MyLoader(Loader):
	def create_module(self,spec):
		
		module = ModuleType(spec.name)
		module.__spec__=spec
		module.__loader__ = self
		module.__path__ = spec.__path__
		return module

	def exec_module(self, module):
		#path = [p+".py" for p in module.__path__]
		name = ""
		code = None
		for n in module.__path__:
			name += n
			name += "."
		if name:
			code = getCodeFromBinary(name[:len(name)-1])

		#this is a class or has code by itself
		if code:
			#print(marshal.loads(bytes(code,"utf-8")))
			#print(type(code))
			exec(code,module.__dict__)
		#this is a module
		# ismodule = getFromDirectory(path+["catalog"])
		# if ismodule:
		# 	for s in ismodule.split(","):
		# 		code = getFromDirectory(path+[s])
		# 		if code:
		# 			exec(code,module.__dict__)


class MyFinder(MetaPathFinder):
	def __init__(self):
		return

	def find_spec(self,fullname,path,target=None):
			
			#print("importing1: "+fullname)
			ans = fullname.split(".")
			currentName=ans[-1]
			for i in range(len(ans)):
				ans[i] += ".py"
			#validate existance from globals
			#this might be wrong
			if not checkCode(fullname):
				return None
			spec = importlib.machinery.ModuleSpec(fullname, MyLoader())
			#update path
			if path:
				spec.__path__ = path + [currentName]
			else:
				spec.__path__ = [currentName]
			# set parent
			if len(ans) == 1:
				if path:
					spec.__parent__=path[-1]
				else:
					spec.__parent__= None
			else:
				spec.__parent__=ans[-1]

			return spec


sys.meta_path.append(MyFinder())
#del sys
#test:
#s imp = ##class(%SYS.Python).Import("customImport")
#s xx = ##class(%SYS.Python).Import("User")

