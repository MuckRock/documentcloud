"""
Writes a `template.yaml` file based on `template_params.yaml` using parameters
from AWS parameter store.

Because `template.yaml` files cannot automatically resolve to the latest
version of a given parameter, we perform a pre-compilation step that involves
using the AWS cli to look up each requested parameter with the latest version
and sub it into the template.

This is a hack until this issue is resolved:
https://github.com/aws-cloudformation/aws-cloudformation-coverage-roadmap/issues/75
"""

import re, json, subprocess, sys, csv

SSM_TOPIC_RE = r'"{{resolve:ssm:([a-zA-Z0-9_./-]+):latest}}"'

# from https://stackoverflow.com/a/8290508
def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx : min(ndx + n, l)]


# Adapted from https://stackoverflow.com/a/4760517
def run_command(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE).stdout.decode("utf-8")


# Begin by processing the parameterized template yaml
with open("template_params.yaml", "r") as f:
    contents = f.read()

# Swap in correct env
env = sys.argv[1]
contents = contents.replace("{$ENV$}", env)

# Get all languages
with open("language_bundles.txt", "r") as f:
    language_bundles = [x for x in f.read().split(" ") if x]
language_topics = ",".join(
    [
        f"ocr-{x.replace('|', '-').strip()}-extraction-{env}".strip()
        for x in language_bundles
    ]
)

# Find each language blocks
def title_case(s):
    if not s:
        return ""
    return s[0].upper() + s[1:]


def titleize(s):
    return "".join([title_case(x) for x in re.split("[^a-zA-Z0-9]+", s) if x])


def topicize(s):
    return "-".join([x for x in re.split("[^a-zA-Z0-9_]+", s) if x])


def fnize(s):
    return "_".join([x for x in re.split("[^a-zA-Z0-9]+", s) if x])


def language_replace(match, languages):
    contents = ""
    for language in languages.split("|"):
        language = language.strip()
        contents += (
            match.group(1)
            .replace("{$TITLE_LANG$}", titleize(language))
            .replace("{$LANG$}", language)
        )
    return contents


def languages_replace(match):
    contents = ""
    for languages in language_bundles:
        languages = languages.strip()
        contents += (
            match.group(1)
            .replace("{$FN_LANGUAGES$}", fnize(languages))
            .replace("{$TITLE_LANGUAGES$}", titleize(languages))
            .replace("{$TOPIC_LANGUAGES$}", topicize(languages))
        )
    return contents


resolved_contents = re.sub(
    r"{{each:LANGUAGES}}\n(.*)\n{{/each:LANGUAGES}}",
    languages_replace,
    contents,
    0,
    re.DOTALL,
)

# Grab all the topics mentioned
topics = list(set(re.findall(SSM_TOPIC_RE, resolved_contents)))

# Build up a topic map
topic_map = {}

for subtopics in batch(topics, 10):
    # AWS can process 10 parameters at a time, so we batch topics
    command = (
        ["aws", "ssm", "get-parameters", "--names"]
        + subtopics
        + ["--query", "Parameters[*].{Name:Name,Value:Value}", "--output", "json"]
    )

    # Run the command to receive multiple parameters at once and update the map
    output = json.loads(run_command(command))
    for value in output:
        topic_map[value["Name"]] = value["Value"]

# A replacement function that subs the resolve expressions with the topic map
def aws_replace(match):
    key_name = match.group(1)
    if (
        key_name not in topic_map
        or not topic_map[key_name]
        or topic_map[key_name].isspace()
    ):
        return '""'
    return topic_map[key_name]


# Resolve the contents and write to template.yaml
resolved_contents = re.sub(SSM_TOPIC_RE, aws_replace, resolved_contents)
resolved_contents = resolved_contents.replace("{$LANGUAGE_TOPICS$}", language_topics)

with open("template.yaml", "w") as f:
    f.write(resolved_contents)
