# Spotifice

This repository contains the starter code for the **Spotifice** application.
Spotifice is a distributed multimedia streaming system built with **ZeroC Ice** and **Python**.

## Requirements

To run this application, you need:

- **Python ≥ 3.10**
- **ZeroC Ice 3.7**
- All Python dependencies listed in the `DEPENDS` file
- A recent GNU/Linux distribution such as **Debian 12 (Bookworm)** or **Ubuntu 23.04** or newer

## Contents

This repository has been cloned as part of an GitHub Classroom assignment. See lab statement in the Moodle course for details.

## Download media files

The `Makefile` will download example music files:

```bash
spotifice$ make
```

## Usage

You can start the application (using `tmux`):

```bash
spotifice$ ./run.sh
```

That executes `media_server`, `media_render` and `media_control` with the proper configuration.


## Authors

Developed by the *Distributed Systems* course teachers at **UCLM-ESI**.
