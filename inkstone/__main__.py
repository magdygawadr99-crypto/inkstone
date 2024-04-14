import os
import sys

from .site import build

src = sys.argv[1] if len(sys.argv) > 1 else "."
print(build(src, os.path.join(src, "public")), "pages")
