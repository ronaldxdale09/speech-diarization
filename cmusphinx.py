import speech_recognition as sr
import pocketsphinx
from pydub import AudioSegment


filename = "chat_with_friends.wav"
r = sr.Recognizer()
with sr.AudioFile(filename) as source:
    audio = r.record(source)


pocketsphinx_transcriber = pocketsphinx.LiveSpeech(
    lm=False,
    hmm='/usr/local/share/pocketsphinx/model/en-us/en-us',
    dic='/usr/local/share/pocketsphinx/model/en-us/cmudict-en-us.dict',
    kws='/usr/local/share/pocketsphinx/model/en-us/spotter/4051.kwlist'
)

for phrase in pocketsphinx_transcriber:
    print(phrase)


def split_on_silence(audio_segment, min_silence_len=1000, silence_thresh=-16):
    "Splits an AudioSegment into chunks where silence is heard."

    segments = []
    current_segment = audio_segment[:0]
    for i, chunk in enumerate(audio_segment[min_silence_len:] for_each_chunk(min_silence_len)):
        silence_start = max(0, i - min_silence_len)
        if audio_segment[silence_start:i].dBFS < silence_thresh:
            segments.append(current_segment)
            current_segment = chunk
        else:
            current_segment += chunk
    segments.append(current_segment)

    return segments

audio_segment = AudioSegment.from_wav(filename)
segments = split_on_silence(audio_segment, min_silence_len=500)

for i, segment in enumerate(segments):
    segment.export("segment_{}.wav".format(i), format="wav")