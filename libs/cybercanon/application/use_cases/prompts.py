"""One prompt per task, in code, versioned with it (D10).

There is no prompt management surface and no per-project tuning, and that is a
decision rather than an omission: a prompt a studio can edit is a prompt nobody
can reproduce a result from, and the two tasks here are narrow enough that the
open question the design records — *how many aliases* — is a number rather than
a paragraph.

**Why these live in the application and not beside the adapter.** D10 puts them
"beside the adapter" and D2 makes the prompt a *parameter* of
:meth:`~cybercanon.application.ports.vision.VisionPort.describe` — and task 2.6
requires `lint-imports` to forbid the application from importing the model
adapter at all. All three cannot hold at once: the layer that passes the prompt
is this one. So the spirit of D10 is kept exactly — one prompt per task, a
constant in code, versioned with the change, no tuning surface — and the letter
of it moves one package, to the only layer that is allowed to reach both the
port and these strings. Putting a copy in the adapter as well would be two
prompts that agree until the day somebody edits one.

Two properties the wording is built around, and both are enforced elsewhere
rather than requested here:

* **The output shape is validated, never trusted.**
  :func:`~cybercanon.domain.derived.parse_aliases` reads the answer defensively
  and reports `malformed` rather than accepting half of it, so a model that
  ignores the instruction below costs a refusal and never a bad alias.
* **Existing aliases are filtered out afterwards**
  (:func:`~cybercanon.domain.derived.normalised_aliases`). The prompt does not
  mention the asset at all — it *cannot*, because the declared scope of image
  description is the image and a fixed instruction, and `llm-integration`
  requires that *"no specification content SHALL be included"*.

That last point is the one worth reading twice. Nothing in this module
interpolates anything. These are constants, and a prompt that took an argument
would be a door for a specification to walk through.
"""

from __future__ import annotations

DESCRIBE_IMAGE = (
    "Describe this concept art in two or three plain sentences. "
    "Say what the subject is, its silhouette and its most recognisable features. "
    "Do not speculate about lore, story or intent. Answer with the description "
    "and nothing else."
)
"""The whole instruction sent beside a concept view for a description.

Fixed, self-contained and about the image only. It names no asset, no project
and no field of a specification, which is what makes the scope requirement a
property of this constant rather than a promise about a call site.
"""

SUGGEST_ALIASES = (
    "Look at this concept art and list the short search terms somebody would "
    "type to find it again. Use single lowercase words or two words joined by an "
    "underscore. Answer with a comma-separated list and nothing else: no "
    "numbering, no bullets, no explanation."
)
"""The instruction for the feature that earns this change.

*"A comma-separated list and nothing else"* is asked for and then **checked**:
provider-agnostic means no structured-output mode and no function calling, so
the answer is text, and the parser fails closed on anything it cannot read as a
list of terms.
"""

TAG_SEPARATOR = ","
"""What the alias prompt asks the model to separate terms with.

Named here beside the prompt that asks for it, so the request and the parser's
most likely input are written down in one place — though the parser accepts
newlines and semicolons too, because a model that was asked for commas will
one day answer with a list.
"""

__all__ = ["DESCRIBE_IMAGE", "SUGGEST_ALIASES", "TAG_SEPARATOR"]
