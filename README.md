# PDF Bind

This is a simple script to combine multiple PDFs into a single one and to create outline with each file being a chapter. 
It uses excellent [pikepdf](https://github.com/pikepdf/pikepdf) library to handle the PDFs.

## Installation
TODO: publish to pypi

After you have built the package, it is recommended to install it using [pipx](https://github.com/pypa/pipx):

```bash
pipx install dist/pdfbind-0.1.0-py3-none-any.whl
```

Of course, you can also install it using standard pip:

```bash
pip install dist/pdfbind-0.1.0-py3-none-any.whl
```


## Buildling

This is a standard Poetry project, so all the usual commands apply:

```bash
poetry install
```

```bash
poetry build
```

## How to use

### 1 Create a layout file

For example, `favorites.yaml`:

```yaml
- file: favorite-tunes/Giant Steps.pdf
- file: favorite-tunes/lennies.pdf
  title: Lennie's Pennies
```

### Run the command

```bash
pdfbind favorites.yaml
```

This command will create `favorites.pdf` in the same directory as the layout file.


## License

Licensed under the Apache License, Version 2.0 (the "License"). See the [LICENSE](LICENSE) file for more details.

Copyright [2024] Sasha Ovsankin
