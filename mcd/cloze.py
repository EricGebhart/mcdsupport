# -*- coding: utf-8 -*-
#
# Portions of this code are derived from the copyrighted works of:
#    Damien Elmes <anki@ichi2.net>
#
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# This project is hosted on GitHub: https://github.com/tarix/mcdsupport

import re

from anki import utils
from anki.consts import *

from aqt import mw


# http://www.peterbe.com/plog/uniqifiers-benchmark
def removeDups(seq):  # Dave Kirby (f8)
    # Order preserving
    seen = set()
    return [x for x in seq if x not in seen and not seen.add(x)]


def listManualSpace(clozes):
    # replace wide spaces
    clozes = unicode.replace(unicode(clozes), u'\u3000', u' ')
    return clozes.split(u' ')


def listManualSemicolon(clozes):
    return clozes.split(u';')


def listKanjiHanzi(clozes):
    return list(clozes)


def nl_br(text):
    return unicode.replace(text, '\n', '<br>')


class Cloze():
    def __init__(self):
        # grab reference to anki globals
        self.mw = mw
        # cloze vars
        self.mode = 0
        self.text = u''
        self.notes = u''
        self.source = u''
        self.clozes = u''
        self.whole_words_only = False
        # anki vars
        self.model = u''
        self.deck = u''
        self.tags = u''
        # status
        self.status = u''

        # :word:foobar
        # :hint:this is foobar
        # :note:this is a note.

    def _getNote(self):
        """get the new note"""
        note = self.mw.col.newNote()

        # set the deck
        if not self.deck.strip():
            note.model()['did'] = 1
        else:
            note.model()['did'] = self.mw.col.decks.id(self.deck)

        # verify this is an Anki 2 cloze model
        if not note.model()['type'] == MODEL_CLOZE:
            self.status = (u'Error: ' +
                           note.model()['name'] +
                           ' is not a Cloze model.')
            return False
        return note

    def _setTags(self, note, fieldmap):
        # set the tags
        note.tags = self.mw.col.tags.split(self.tags)
        # deal with the source field
        if len(self.source):
            source_id = fieldmap.get('Source', None)
            if source_id:
                note.fields[source_id[0]] = self.source
            else:
                self.notes = self.notes + u'<br><br>' + self.source

    def _checkJapaneseReading(self, note, fieldmap):
        # check for a reading field
        reading_id = fieldmap.get('Reading', None)
        if reading_id:
            try:
                from japanese.reading import mecab
                note.fields[reading_id[0]] = mecab.reading(reading)
            except:
                self.status = (u'Error: Unable to generate the reading.' +
                               u'Please install the Japanese Support Plugin.')
                return False
        return True

    def _statusSucces(self, closeCount):
        excerpt = self.text[:10]
        excerpt = excerpt.replace(u'\n', u' ')
        if len(self.text) > 10:
            excerpt += u'...'
        prefix = u'Added a new note \'{0}\' with {1} cloze{2}'
        suffix = u's.'
        if closeCount <= 1:
            suffix = u'.'
        self.status = prefix.format(excerpt, closeCount, suffix)

    def _generateClozeList(self):
        """generate a cloze list solely based on the notes.
        The words are preceded by .. and the hints by --.
        Additional notes are left alone. """
        word = u''
        hint = u''
        note = u''
        listClozes = []
        wordkey = u'..'  # u':word'
        hintkey = u'--'  # u':hint'
        for line in self.notes.splitlines():
            key = line[:2]
            text = line[2:].strip()
            if key == wordkey:
                if len(word) >= 1:
                    listClozes.append({'word': word, 'hint': hint})
                hint = u''
                word = text
            elif key == hintkey:
                hint = text
        else:
            if len(word) >= 1:
                listClozes.append({'word': word, 'hint': hint})
        return listClozes

    def _generateClozeList_orig(self):
        """The original cloze list creation function.
        this one uses the cloze field on the form and cannot
        do hints."""

        # Manual (space delimeter)
        if self.mode == 'space':
            listClozes = listManualSpace(self.clozes)

        # Manual (semicolon delimeter)
        elif self.mode == 'semicolon':
            listClozes = listManualSemicolon(self.clozes)

        # Kanji/Hanzi
        elif self.mode == 'kanji':
            listClozes = listKanjiHanzi(self.clozes)

        # remove any empty (whitespace only) entries
        listClozes = [clz for clz in listClozes if clz.strip()]
        # remove duplicates
        listClozes = removeDups(listClozes)
        return listClozes

    def _clozeReplace(self, text, cloze, cloze_text):
        # process the replacement based on user options
        if self.whole_words_only:
            return re.sub(ur'\b{}\b'.format(cloze),
                          cloze_text, text, flags=re.UNICODE)
        else:
            return unicode.replace(text, cloze, cloze_text)

    def _clozePrepare(self, text, cloze, hint, num):
        # replace the text with a cloze sub
        cloze_stub = u'{{c%d::' % num + u'::%s}}' % hint
        return self._clozeReplace(text, cloze, cloze_stub)

    def _clozeFinalize(self, text, cloze, hint, num):
        # replace the subs with the final cloze
        cloze_stub = u'{{c%d::' % num + u'::%s}}' % hint
        cloze_text = u'{{c%d::' % num + cloze + u'::%s}}' % hint
        return unicode.replace(text, cloze_stub, cloze_text)

    def _preprocessClozes(self, listClozes):
        # pre-process all of the closes
        for i, clz in enumerate(listClozes):
            self.text = self._clozePrepare(self.text,
                                           clz['word'],
                                           clz['hint'], i+1)

        # finalize the clozes, this two stage process prevents
        # errors with embedded clozes
        for i, clz in enumerate(listClozes):
            self.text = self._clozeFinalize(self.text,
                                            clz['word'],
                                            clz['hint'], i+1)

    def createNote(self):
        # create the new note
        note = self._getNote()

        if not note:
            return False

        fieldmap = self.mw.col.models.fieldMap(note.model())

        # grab part of the card for the status update
        # create a list of cloze candidates before the
        # newlines are converted.
        listClozes = self._generateClozeList()

        # convert the newlines to html
        self.text = nl_br(self.text)
        self.notes = nl_br(self.notes)
        self.source = nl_br(self.source)

        # save the text for the reading generation
        reading = self.text

        # cheat and put the cloze list in the card to see what is happening.
        # self.notes = str(listClozes)

        # process the clozes.
        self._preprocessClozes(listClozes)

        self._setTags(note, fieldmap)

        if not self._checkJapaneseReading(note, fieldmap):
            return False

        # fill in the note fields
        note.fields[0] = self.text
        note.fields[1] = self.notes

        # check for errors
        if note.dupeOrEmpty():
            self.status = u'Error: Note is empty or a duplicate.'
            return False

        # add the new note
        cards = self.mw.col.addNote(note)
        if not cards:
            self.status = (u'Error:' +
                           u'This note was not able to generate any cards.')
            return False

        # flag the queue for reset
        self.mw.requireReset()
        # save the collection
        self.mw.col.autosave()
        # set the status
        self._statusSucces(len(listClozes))
        # return success
        return True
