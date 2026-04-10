"""CI task definitions for the project workflow."""

from invoke import Collection

from . import build
from . import container
from . import develop
from . import document
from . import format_
from . import lint
from . import quality
from . import secure
from . import test

namespace = Collection()
namespace.add_collection(build.namespace)
namespace.add_collection(container.namespace)
namespace.add_collection(develop.namespace)
namespace.add_collection(document.namespace)
namespace.add_collection(format_.namespace)
namespace.add_collection(lint.namespace)
namespace.add_collection(quality.namespace)
namespace.add_collection(secure.namespace)
namespace.add_collection(test.namespace)
