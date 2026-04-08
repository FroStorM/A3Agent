import importlib.util, inspect
with open("mykey_test.py", "w") as f:
    f.write("a = 1\n")
spec = importlib.util.spec_from_file_location("test_mod", "mykey_test.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
try:
    print(inspect.getsource(mod))
except Exception as e:
    print("Error:", e)
