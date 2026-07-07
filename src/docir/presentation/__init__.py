# Presentation layer — the Typer/Rich CLI and the composition root.
#
# This is the outermost ring and the only place allowed to know about every
# other layer at once: the composition root (`composition`) wires concrete
# infrastructure adapters into the application use cases, and the CLI (`cli`)
# translates command-line input into requests and renders the responses.
