ifeq ($(OS),Windows_NT)
    PYTHON = py
    OPEN_CMD = start cmd /k
else
    PYTHON = python3
endif

.PHONY: server client client2 client3 open-clients

server:
	$(PYTHON) -m network_project.server.server

client:
	$(PYTHON) -m network_project.client.client

client2:
	$(PYTHON) -m network_project.client.client2

client3:
	$(PYTHON) -m network_project.client.client3

open-clients:
	$(OPEN_CMD) "$(PYTHON) -m network_project.client.client"
	$(OPEN_CMD) "$(PYTHON) -m network_project.client.client2"
	$(OPEN_CMD) "$(PYTHON) -m network_project.client.client3"