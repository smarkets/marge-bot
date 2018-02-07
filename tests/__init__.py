import logging

# reduce noise, see: https://github.com/eisensheng/pytest-catchlog/issues/59
logging.getLogger('flake8').propagate = False
