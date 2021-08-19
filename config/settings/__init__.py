from .base import *  # noqa

if STAGE == "production":  # noqa
    from .production import *  # noqa
elif STAGE == "staging":  # noqa
    from .staging import *  # noqa
else:
    from .local import *  # noqa
