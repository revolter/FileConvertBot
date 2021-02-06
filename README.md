# <img src="/images/logo.png" width="28"/> File Convert Bot

## Introduction

Telegram Bot that converts _(for now)_ AAC, OPUS, MP3 and WebM files to voice
messages, HEVC and MP4 (MPEG4, VP6 and VP8) files to video messages or video
notes (rounded ones), video messages to video notes (rounded ones), videos from
some websites to video messages, PDF files to photo messages _(currently only
the first page)_, image files to stickers. It also converts voice messages to
MP3 files and stickers to photo messages. It works in groups too!

The bot currently runs as [@FileConvertBot](https://t.me/FileConvertBot).

**All the processing is done in-memory, so no file is ever saved on the disk,
not even temporary!**

## Getting Started

These instructions will get you a copy of the project up and running on your
local machine for development and testing purposes.

### Prerequisites

You need to install [Homebrew](https://brew.sh) by running:

```sh
/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
```

### Installing

Clone the project and install the dependencies by running:

```sh
cd /desired/location/path
git clone https://github.com/kuanidonya/FileConvertBot.git
cd FileConvertBot

curl https://pyenv.run | bash

pyenv install 3.9.0
pyenv global 3.9.0

curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3
poetry shell
poetry install

cd src
cp config_sample.cfg config.cfg
```

Then, edit the file named `config.cfg` inside the `src` folder with the correct
values and run it using `./main.py --debug`.

Use `exit` to close the virtual environment.

## Deploy

You can easily deploy this to a cloud machine using
[Fabric](http://fabfile.org):

```
cd /project/location/path

poetry shell

cp fabfile_sample.cfg fabfile.cfg
```

Then, edit the file named `fabfile.cfg` inside the root folder with the correct
values and run Fabric using:

```
fab setup
fab deploy
```

You can also deploy a single file using `fab deploy --filename=main.py` or `fab
deploy --filename=pyproject.toml`.

## Dependencies

Currently, you have to manually install `poppler` in order for `PDF` to `PNG`
conversion to work:

- macOS: `brew install poppler`
- Ubuntu: `sudo apt-get install poppler-utils`
