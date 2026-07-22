# Module entry point: enables `python -m docir ...`, which is how the daemon
# lifecycle spawns its detached background process.

from docir.entry_points.cli.app import main

if __name__ == "__main__":
    main()
