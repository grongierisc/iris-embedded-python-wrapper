import sys
from os import sep as __os_sep
from site import getsitepackages as __sitegetsitepackages

#ubuntu needs dist-packages for pandas to be able to be imported
#ubu 18 doesnt have os.sep in sys.executable
def set_site_path(platform_name):
   if "ubuntu" in platform_name:
      if __os_sep in sys.executable:
         __siteprefixes = [__os_sep + sys.executable.split(__os_sep)[1]]
      else:
         __siteprefixes = ['/usr']
      sys.path = sys.path + __sitegetsitepackages(__siteprefixes)
