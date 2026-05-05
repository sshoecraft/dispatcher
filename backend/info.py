
import json
import os
import socket
from output import output

# Single source of truth for branding/identity. The fork only edits this file
# (and swaps SVGs in frontend/public/branding/) — no source-code changes.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BRANDING_PATH = os.path.join(_REPO_ROOT, 'branding.json')

_BRANDING_DEFAULTS = {
	"slug": "dispatcher",
	"appName": "Dispatcher",
	"appShortName": "Dispatcher",
	"htmlTitle": "Dispatcher",
}


def _load_branding():
	try:
		with open(_BRANDING_PATH, 'r') as f:
			data = json.load(f)
		return {**_BRANDING_DEFAULTS, **data}
	except (OSError, ValueError) as e:
		output.warning(f"Could not load {_BRANDING_PATH}: {e}; using defaults")
		return dict(_BRANDING_DEFAULTS)


class Info:
	def __init__(self):
		self.branding = _load_branding()
		# slug is the lowercase identifier used for paths (~/.<slug>),
		# log labels, and any system-level naming.
		self.name = self.branding["slug"]
		self.app_name = self.branding["appName"]
		self.desc = self.branding.get("appShortName", self.app_name)
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
