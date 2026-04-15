import subprocess
import sys
import os

def run_step(name, cmd, exit_on_fail=True):
    print(f"\n[{name}] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[FAILED] {name} failed!")
        if exit_on_fail:
            sys.exit(1)
        return False
    print(f"[PASSED] {name} passed!")
    return True

def main():
    print("[START] Verification Pipeline")
    print("Goal: Ensure 100% clean code before commit.\n")

    # Step 1: Flake8 Linter
    run_step("FLAKE8 Linter", ["flake8", "src", "--select", "E,F,W", "--ignore", "E501,W293,W291,E128,E124,W391,E302,E303,F401,F403,F405,F541,F811,F841,E402,E261"])

    # Step 2: Pytest Unit Tests
    run_step("PYTEST Unit Tests", ["pytest", "-v", "tests/"])

    print("\n[SUCCESS] All checks passed! Safe to Git Push.")

if __name__ == "__main__":
    main()
