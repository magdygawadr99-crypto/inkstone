from __future__ import annotations

import pytest

from inkstone.search import stem
from inkstone.search.stemmer import _regions


def pairs(table: str) -> list[tuple[str, str]]:
    return [tuple(item.split("=")) for item in table.split()]


# The two runs of consecutive vocabulary shown on the Porter2 page at
# snowballstem.org, which makes them the closest thing to a reference here.
SNOWBALL_SAMPLE = pairs("""
    consign=consign consigned=consign consigning=consign consignment=consign
    consist=consist consisted=consist consistency=consist consistent=consist
    consistently=consist consisting=consist consists=consist consolation=consol
    consolations=consol consolatory=consolatori console=consol consoled=consol
    consoles=consol consolidate=consolid consolidated=consolid
    consolidating=consolid consoling=consol consolingly=consol consols=consol
    consonant=conson consort=consort consorted=consort consorting=consort
    conspicuous=conspicu conspicuously=conspicu conspiracy=conspiraci
    conspirator=conspir conspirators=conspir conspire=conspir conspired=conspir
    conspiring=conspir constable=constabl constables=constabl constance=constanc
    constancy=constanc constant=constant
    knack=knack knackeries=knackeri knacks=knack knag=knag knave=knave
    knaves=knave knavish=knavish kneaded=knead kneading=knead knee=knee
    kneel=kneel kneeled=kneel kneeling=kneel kneels=kneel knees=knee knell=knell
    knelt=knelt knew=knew knick=knick knif=knif knife=knife knight=knight
    knightly=knight knights=knight knit=knit knits=knit knitted=knit
    knitting=knit knives=knive knob=knob knobs=knob knock=knock knocked=knock
    knocker=knocker knockers=knocker knocking=knock knocks=knock knopp=knopp
    knot=knot knots=knot
    """)

PLURALS = pairs("""
    caresses=caress caress=caress ponies=poni ties=tie cries=cri dies=die
    cats=cat gaps=gap kiwis=kiwi gas=gas this=this bus=bus buses=buse
    classes=class class=class analysis=analysi was=was has=has users=user
    wolves=wolv leaves=leav mysteries=mysteri
    """)

ED_AND_ING = pairs("""
    feed=feed agreed=agre plastered=plaster bled=bled motoring=motor sing=sing
    conflated=conflat troubled=troubl sized=size hopping=hop tanned=tan
    falling=fall hissing=hiss fizzed=fizz failing=fail filing=file hoping=hope
    running=run skiing=ski died=die applied=appli replied=repli dried=dri
    using=use used=use going=go luxuriously=luxuri consolingly=consol
    exceedingly=exceed stayed=stay playing=play toying=toy
    """)

Y_HANDLING = pairs("""
    happy=happi cry=cri fly=fli apply=appli by=by say=say boy=boy enjoy=enjoy
    yes=yes yellow=yellow yearly=year youth=youth beyond=beyond lawyer=lawyer
    kayak=kayak cycle=cycl mystery=mysteri daily=daili
    """)

DERIVATIONS = pairs("""
    relational=relat conditional=condit rational=ration national=nation
    valenci=valenc hesitanci=hesit digitizer=digit conformabli=conform
    radicalli=radic differentli=differ vileli=vile analogousli=analog
    vietnamization=vietnam predication=predic operator=oper feudalism=feudal
    decisiveness=decis hopefulness=hope callousness=callous formaliti=formal
    sensitiviti=sensit sensibiliti=sensibl triplicate=triplic formative=format
    formalize=formal electricity=electr electrical=electr hopeful=hope
    goodness=good revival=reviv allowance=allow inference=infer airliner=airlin
    gyroscopic=gyroscop adjustable=adjust defensible=defens irritant=irrit
    replacement=replac adjustment=adjust dependent=depend adoption=adopt
    homologous=homolog effective=effect bowdlerize=bowdler activate=activ
    angulariti=angular probate=probat rate=rate cease=ceas controll=control
    roll=roll nationality=nation nationalism=nation rationalize=ration
    organization=organ organizer=organ organize=organ accessibility=access
    abandonment=abandon absolutely=absolut quickly=quick easily=easili
    nicely=nice possibly=possibl possible=possibl simply=simpli simple=simpl
    argument=argument arguing=argu argue=argu beautiful=beauti beauty=beauti
    university=univers abilities=abil connection=connect happiness=happi
    hopefully=hope statically=static searches=search indexes=index
    """)

# R1 is moved for these prefixes so that the suffix rules leave them alone.
SPECIAL_REGIONS = pairs("""
    generate=generat generation=generat generator=generat generated=generat
    generating=generat generic=generic general=general generously=generous
    generalization=general communism=communism communication=communic
    communal=communal arsenic=arsenic arsenal=arsenal
    """)

EXCEPTIONS = pairs("""
    skis=ski skies=sky sky=sky dying=die lying=lie tying=tie idly=idl
    gently=gentl ugly=ugli early=earli only=onli singly=singl news=news
    howe=howe atlas=atlas cosmos=cosmos bias=bias andes=andes inning=inning
    innings=inning outing=outing canning=canning herring=herring
    herrings=herring earring=earring proceed=proceed proceeds=proceed
    exceed=exceed exceeding=exceed succeed=succeed succeeding=succeed
    """)

STEMS = (
    SNOWBALL_SAMPLE
    + PLURALS
    + ED_AND_ING
    + Y_HANDLING
    + DERIVATIONS
    + SPECIAL_REGIONS
    + EXCEPTIONS
)


@pytest.mark.parametrize(("word", "expected"), STEMS, ids=[word for word, _ in STEMS])
def test_stem(word, expected):
    assert stem(word) == expected


@pytest.mark.parametrize("word", ["", "a", "is", "be", "of", "ox", "'s", "as"])
def test_words_of_two_letters_or_fewer_are_left_alone(word):
    assert stem(word) == word.lstrip("'")


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("dog's", "dog"),
        ("dogs'", "dog"),
        ("dog's'", "dog"),
        ("dog\u2019s", "dog"),
        ("'twas", "twas"),
        ("o'clock", "o'clock"),
    ],
)
def test_apostrophes(word, expected):
    assert stem(word) == expected


def test_input_is_lowercased():
    assert stem("Running") == "run"
    assert stem("GENERATIONS") == "generat"


@pytest.mark.parametrize("word", ["python3", "utf8", "c++", "3.14", "x86", "h264"])
def test_words_with_digits_and_symbols_survive(word):
    assert stem(word) == word


@pytest.mark.parametrize("word", ["москва", "ελληνικά", "日本語", "naïveté"])
def test_words_without_english_endings_pass_through(word):
    assert stem(word) == word


def test_stemming_a_stem_again_changes_little():
    # Porter2 is not idempotent in general, but the common vocabulary of a
    # blog should not keep shrinking when a stem is fed back in as a query.
    for word in ("generation", "running", "searching", "indexes", "quickly"):
        once = stem(word)
        assert stem(once) == once


@pytest.mark.parametrize(
    ("word", "r1", "r2"),
    [
        ("beautiful", "iful", "ul"),
        ("beauty", "y", ""),
        ("beau", "", ""),
        ("animadversion", "imadversion", "adversion"),
        ("sprinkled", "kled", ""),
        ("eucharist", "harist", "ist"),
        ("generate", "ate", "e"),
        ("communion", "ion", ""),
    ],
)
def test_regions(word, r1, r2):
    start1, start2 = _regions(word)
    assert (word[start1:], word[start2:]) == (r1, r2)
