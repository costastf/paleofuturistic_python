import os
import stat

os.chmod('workflow.cmd', os.stat('workflow.cmd').st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
