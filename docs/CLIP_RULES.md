# What makes a good clip

These are the rules ClipForge's AI is given when it picks moments and cuts them (see `studio/brain.py`,
`CLIP_RULES`). Change them here and in the code together.

## The start: the hook (first 3 seconds)
- Open on the line that makes a stranger stop scrolling: a bold claim, a question, the start of a fight or a play,
  a surprising fact, or the setup of a punchline.
- Never open with filler ("so", "okay guys", "anyway", "yeah"), a greeting, or the middle of an answer.
- If the moment needs context, the first sentence must give it quickly. Context that takes longer than one or two
  sentences means the clip starts too early.

## The middle
- One idea, one story, one play. Cut tangents; a clip that changes topic is two clips or none.

## The end: the payoff
- End right after the payoff: the punchline, the reveal, the last sentence of the answer, the play's result, or
  the reaction to it (a laugh, a scream, "no way"), plus at most a second or two of that reaction.
- Never end on a setup, a question left hanging, half a sentence, or the first words of the next topic.
- The last line should feel final when read alone: a punchline, a strong statement, a verdict, a laugh.

## Length
- As long as the moment needs and no longer: usually 20 to 45 seconds. Never padded to reach a length.
