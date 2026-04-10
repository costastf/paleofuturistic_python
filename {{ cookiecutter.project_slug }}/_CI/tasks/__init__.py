"""CI task definitions for the project workflow."""

from invoke import Collection

from . import build as _build
from . import container as _container
from . import document as _document
from . import format_ as _format
from . import lint as _lint
from . import quality as _quality
from . import secure as _secure
from . import test as _test

namespace = Collection()
namespace.add_collection(_build.namespace)
namespace.add_collection(_container.namespace)
namespace.add_collection(_document.namespace)
namespace.add_collection(_format.namespace)
namespace.add_collection(_lint.namespace)
namespace.add_collection(_quality.namespace)
namespace.add_collection(_secure.namespace)
namespace.add_collection(_test.namespace)
