"""Safe ESP32 application entry point for deployment-channel verification."""


def main():
    """Report a safe startup without initializing motion hardware."""
    print("robot-platform ESP32 baseline: no motion hardware initialized")


if __name__ == "__main__":
    main()
