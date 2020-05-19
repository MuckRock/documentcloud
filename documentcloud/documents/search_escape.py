# Standard Library
import re

is_java_identifier_part = re.compile(r"[a-zA-Z0-9$_]")

# pylint: disable=too-many-branches, too-many-statements, no-else-continue


def split_into_clauses(query, ignore_quote=False):
    lst = []
    pos = 0
    end = len(query)
    char = None

    while pos < end:
        clause = {}
        disallow_user_field = True
        char = query[pos]

        while char.isspace():
            pos += 1
            if pos >= end:
                break
            char = query[pos]

        start = pos

        if char in ("+", "-") and pos + 1 < end:
            clause["must"] = char
            pos += 1

        clause["field"] = get_field_name(query, pos, end)
        if clause["field"] is not None:
            disallow_user_field = False
            colon = query.find(":", pos)
            clause["raw_field"] = query[pos:colon]
            pos += colon - pos  # skip the field
            pos += 1  # skip the ':'

        if pos >= end:
            break

        in_string = None
        char = query[pos]
        if not ignore_quote and char == '"':
            clause["is_phrase"] = True
            in_string = '"'
            pos += 1

        string_builder = []
        while pos < end:
            char = query[pos]
            pos += 1
            if char == "\\":
                # skip escaped character
                string_builder.append(char)
                if pos >= end:
                    string_builder.append(char)  # double backslash
                    break
                char = query[pos]
                pos += 1
                string_builder.append(char)
                continue
            elif in_string is not None and char == in_string:
                in_string = None
                break
            elif char.isspace():
                clause["has_whitespace"] = True
                if in_string is None:
                    # end of the token if we aren't in a string, backing
                    # up the position.
                    pos -= 1
                    break

            if in_string is None:
                if char in '!():^[]{}~*?"+-\\|&/':
                    string_builder.append("\\")
            elif char == '"':
                # only char we need to escape in a string is double quote
                string_builder.append("\\")
            string_builder.append(char)
        clause["val"] = "".join(string_builder)

        if clause.get("is_phrase"):
            if in_string is not None:
                # detected bad quote balancing... retry
                # parsing with quotes like any other char
                return split_into_clauses(query, True)
        else:
            # an empty clause... must be just a + or - on its own
            if not clause["val"]:
                clause["syntax_error"] = True
                if "must" in clause:
                    clause["val"] = "\\" + clause["must"]
                    clause["must"] = None
                else:
                    # uh.. this shouldn't happen.
                    clause = None

        if clause is not None:
            if disallow_user_field:
                clause["raw"] = query[start:pos]
                # escape colons, except for "match all" query
                if clause["raw"] != "*:*":
                    clause["raw"] = re.sub(r"([^\\]):", r"\g<1>\:", clause["raw"])
            else:
                clause["raw"] = query[start:pos]
                # ignore adding boost
            clause["pos"] = [start, pos]
            lst.append(clause)

    return lst


def get_field_name(query, pos, end):
    if pos >= end:
        return None

    cur_pos = pos
    colon = query.find(":", pos)
    # make sure there is space after the colon, but not whitespace
    if colon <= pos or colon + 1 >= end or query[colon + 1].isspace():
        return None
    char = query[cur_pos]
    cur_pos += 1
    while char in "(+=" and pos < end:
        char = query[cur_pos]
        cur_pos += 1
        pos += 1

    if not is_java_identifier_part.match(char):
        return None
    while cur_pos < colon:
        char = query[cur_pos]
        cur_pos += 1
        if not (is_java_identifier_part.match(char) or char in "-."):
            return None

    return query[pos:cur_pos]


def escape_user_query(clauses):
    string_builder = []
    for clause in clauses:
        do_quote = clause.get("is_phrase", False)

        if not do_quote and clause["val"] in ("OR", "AND", "NOT"):
            do_quote = True

        if clause.get("must"):
            string_builder.append(clause["must"])
        if clause["field"] is not None:
            string_builder.append(clause["field"])
            string_builder.append(":")

        if do_quote:
            string_builder.append('"')
        string_builder.append(clause["val"])
        if do_quote:
            string_builder.append('"')

        string_builder.append(" ")

    return "".join(string_builder).strip()


def escape(query):
    clauses = split_into_clauses(query)
    return escape_user_query(clauses)
