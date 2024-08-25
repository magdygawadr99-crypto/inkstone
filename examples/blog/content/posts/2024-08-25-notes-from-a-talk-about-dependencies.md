---
title: Notes from a talk about dependencies, by someone who counts them
description: A meetup talk that agreed with me, then made me less sure I was right.
tags: [talks, dependencies, asides]
categories: [asides]
---

Our local Python meetup had a talk on Thursday called *"Every dependency is
a hire"*. I went because the title sounded like it would agree with me, and
it did, for about ten minutes. These are my notes, tidied up on the train
home.

<!-- more -->

The speaker maintains the internal platform at a mid-sized company:
around 300 services, most of them Python. She opened with a slide that was
just a number: **2,140**. That is how many distinct packages their services
install, counting transitive ones. The services *import* 190 of them
directly.

## The argument

The title is the argument. When you add a dependency you are not taking on
code, you are taking on the people who write it: their release schedule,
their taste in breaking changes, how they answer a security report on a
Friday. You would interview a person before giving them commit access.
A dependency gets it after one `pip install`.

Her list of questions before adding one, which I copied off the slide:

1. Could we write the part we need in an afternoon?
2. Who maintains it, and how many of them are there?
3. What does *it* depend on?
4. When it breaks, can we read the source and fix it ourselves?
5. What is the plan for removing it?

Nobody in the room had ever answered number five for anything.

## Where it stopped agreeing with me

I was nodding along, composing a smug paragraph about inkstone and its zero
dependencies, when she put up the counter-slide.

> The alternative to a dependency is not "no code". It is code you wrote,
> that only you have read, with the bugs only you will find.

Her team had replaced a small date-parsing library with their own forty
lines. It was faster, it had no transitive dependencies, and it was wrong
about the last week of December in a way the library had fixed in 2016.

{{< note title="The bit I wrote down twice" >}}
"Not invented here" and "invented here, badly" are the same mistake made in
opposite directions. The question is never *dependency or not*. It is *who do
I want to be responsible for this, and am I honest about it being me*.
{{< /note >}}

That is a fair description of what I am doing. I have written a YAML
parser. People who have spent years on YAML parsers still find bugs in
theirs. Mine is four months old and has one user.

The difference, and I think she would accept this: it is a blog. The blast
radius of a bug is a wrong date on a post about parsers. Nobody is routing
freight with it.

## Things I am taking away

- Count transitive dependencies, not direct ones. `pip freeze | wc -l` is
  the honest number.
- "Could we write it in an afternoon" has a follow-up: "and will we maintain
  it for five years". Usually the first answer is yes and the second is no.
- Standard libraries are dependencies too, with unusually good maintainers.
  That one made me feel better.
- Write down *why* each dependency is there, next to where it is declared.
  A comment in the requirements file is enough.

## Further watching

The talk was not recorded. She said the framing owes a lot to Rich Hickey's
*Simple Made Easy*, which is on YouTube and worth an hour of anyone's time,
whatever language you write:

{{< youtube id="SxdOUGdseq4" title="Simple Made Easy, Rich Hickey, Strange Loop 2011" >}}

"Easy" is near to hand; "simple" is not tangled up with other things.
`pip install` is easy. I spent the rest of the train ride wondering whether
inkstone is simple, or just mine.
