import os
import stat

os.chmod('workflow', os.stat('workflow').st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
