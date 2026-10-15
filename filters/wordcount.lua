-- Prints body / footnote / total word counts. Run via `make wordcount`.
-- Body includes headings; footnotes are counted separately. Front matter
-- (title, author note, abstract) is not counted.
-- A heading written `# Title {.nocount}` excludes that section (up to the next heading of
-- the same or higher level) from the count, for parts a court's rules leave out.
-- Set WORDCOUNT_JSON=path to also write the numbers as JSON (used by CI).

local function count(el)
  local n = 0
  el:walk { Str = function(s) if s.text:match('%w') then n = n + 1 end end,
            Code = function(c) n = n + select(2, c.text:gsub('%S+', '')) end }
  return n
end

local function drop_nocount(blocks)
  local out, skip = pandoc.List{}, nil
  for _, b in ipairs(blocks) do
    if b.t == 'Header' then
      if skip and b.level <= skip then skip = nil end
      if not skip and b.classes:includes('nocount') then skip = b.level end
    end
    if not skip then out:insert(b) end
  end
  return out
end

function Pandoc(doc)
  doc.blocks = drop_nocount(doc.blocks)
  local notes = 0
  local body_doc = doc:walk {
    Note = function(n)
      notes = notes + count(pandoc.Div(n.content))
      return pandoc.Str('')
    end
  }
  local body = count(pandoc.Div(body_doc.blocks))
  local nfoot = 0
  doc:walk { Note = function() nfoot = nfoot + 1 end }
  io.stderr:write(string.format(
    'Words: %d body + %d footnotes = %d total  (%d footnotes)\n',
    body, notes, body + notes, nfoot))
  local out = os.getenv('WORDCOUNT_JSON')
  if out then
    local f = io.open(out, 'w')
    f:write(pandoc.json.encode({ body = body, footnotes = notes,
                                 total = body + notes, footnote_count = nfoot }))
    f:close()
  end
  return doc
end
