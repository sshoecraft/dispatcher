
import os
import socket
from output import output

class Info:
	def __init__(self):
		self.name = "dispatcher"
		self.desc = "see: name"
		self.version = "1.1"
		self.prefix = None
		self.http_port = int(os.getenv('NGINX_HTTP', '80'))
		self.https_port = int(os.getenv('NGINX_HTTPS', '443'))
		self.port = int(os.getenv('FASTAPI', '8000'))

	def set_prefix(self,prefix = None):
		if prefix:
			self.prefix = prefix;
		else:
			self.prefix = os.getenv('PREFIX', os.path.expanduser("~/."+self.name))
		output.info("prefix set to: "+self.prefix)

	def get_local_ip(self):
		"""Get the local IP address that can be reached by other machines"""
		try:
			# Connect to a remote address to determine the local IP
			# This doesn't actually send data, just determines routing
			with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
				s.connect(("8.8.8.8", 80))
				return s.getsockname()[0]
		except Exception as e:
			output.warning(f"Could not determine local IP: {e}")
			return "localhost"

info = Info()
