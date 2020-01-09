# Third Party
import environ

env = environ.Env()

# Imports based on execution context
if env.str("ENVIRONMENT").startswith("local"):
    from documentcloud.common.session import session as httpsub
else:
    from common.session import session as httpsub
