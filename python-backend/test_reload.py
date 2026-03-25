import sys, importlib, os
sys.path.insert(0, os.path.abspath("."))
import sidercall
import llmcore
import agentmain

agent1 = agentmain.GeneraticAgent()
print("Initial models:", len(agent1.llmclient.backends) if agent1.llmclient else 0)

with open("mykey.py", "a") as f:
    f.write("oai_config_test2 = {'apikey': '123', 'apibase': 'test', 'model': 'test'}\n")

if "mykey" in sys.modules:
    del sys.modules["mykey"]
if "llmcore" in sys.modules:
    importlib.reload(sys.modules["llmcore"])
if "sidercall" in sys.modules:
    importlib.reload(sys.modules["sidercall"])
if "agentmain" in sys.modules:
    importlib.reload(sys.modules["agentmain"])

import agentmain
agent2 = agentmain.GeneraticAgent()
print("After reload:", len(agent2.llmclient.backends) if agent2.llmclient else 0)
