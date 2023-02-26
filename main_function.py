

## ==> GUI FILE

from PyQt5 import QtCore
from PyQt5.QtCore import QPropertyAnimation, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QTableWidgetItem
import PyQt5.QtCore  
from PyQt5.QtWidgets import QMessageBox
import os
from datetime import datetime, timedelta
import mysql.connector
from PySide2.QtWidgets import *
from PyQt5.QtGui import QPixmap
import matplotlib.pyplot as plt
from main import MainWindow
import numpy   as np
import os
from demo_utils import *
from pathlib import Path
from pydub import AudioSegment
from resemblyzer import preprocess_wav, VoiceEncoder
from sklearn.cluster import SpectralClustering
import numpy as np
import os
import wave
from vosk import Model, KaldiRecognizer, SetLogLevel
import json
from resemblyzer import sampling_rate
import pyaudio
import ffmpeg
# pip install webrtcvad-wheels
from scipy.io import wavfile
from main import * 
from sklearn.metrics.pairwise import cosine_similarity

SetLogLevel(-1)

class SpeechThread(QThread):
    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui

    


    def run(self):

        #get the selected model 
        selected_model = self.ui.selectModel.currentText()

        if selected_model == "English 1" :
            trans_model = "vosk-model-en-us-daanzu-20200328"
        elif selected_model == "English 2" :
            trans_model = "vosk-model-en-us-aspire-0.2"
        elif selected_model == "Filipino" :
            trans_model = "vosk-model-tl-ph-generic-0.6"

        # get the file
        filename = self.ui.uploadFilename.text()
        output_dir = 'uploads'
        os.makedirs(output_dir, exist_ok=True)
        FFMPEG_PATH = "fmpeg\bin\ffmpeg.exe"

        # Check if the file is already a mono WAV file
        file_extension = os.path.splitext(filename)[1].lower()
        if file_extension == ".wav":
            with wave.open(filename, "rb") as wf:
                nchannels, sampwidth, framerate, nframes, comptype, compname = wf.getparams()
                if nchannels == 1:
                    sampling_rate = framerate
                    audio_segment = AudioSegment.from_file(filename, format="wav")
                else:
                    # Convert stereo WAV file to mono
                    print("> Converting stereo WAV file to mono")
                    sound = AudioSegment.from_file(filename, format="mp3")
                    sound = sound.set_channels(1)
                    new_filename = os.path.join(output_dir, os.path.splitext(os.path.basename(filename))[0] + ".wav")
                    sound.export(new_filename, format="wav")
                    filename = new_filename
                    sampling_rate, wav = wavfile.read(filename)

        # Convert MP3 file to mono WAV
        elif file_extension == ".mp3" or file_extension == ".mp4":
            print("> Converting to mono WAV")
            sound = AudioSegment.from_file(filename)
            sound = sound.set_channels(1)
            new_filename = os.path.join(output_dir, os.path.splitext(os.path.basename(filename))[0] + ".wav")
            sound.export(new_filename, format="wav")
            filename = new_filename
            sampling_rate, wav = wavfile.read(filename)


                # Transcription
  
        # Initialize the voice encoder
        encoder = VoiceEncoder()
        # Load the audio file
        audio = AudioSegment.from_file(filename, format="wav")

        # Extract the audio data as a numpy array
        audio_data = np.array(audio.get_array_of_samples())
        audio_data = audio_data.astype(np.float32)

        # Preprocess the audio data and extract continuous embeddings
        preprocessed_wav = preprocess_wav(audio_data, 16000)
        _, cont_embeds, wav_splits = encoder.embed_utterance(preprocessed_wav, return_partials=True)

        # Convert cont_embeds to float64 type
        cont_embeds = np.array(cont_embeds).astype(np.float64)

        # Cluster the embeddings to identify the number of speakers
        similarity_measure = 'cosine'
        affinity_matrix = np.matmul(cont_embeds, cont_embeds.T)
        gamma = 1.0
        n_clusters = 2
        spectral = SpectralClustering(
            n_clusters=n_clusters,
            assign_labels='discretize',
            affinity='rbf',
            n_init=100,
            eigen_tol=0.0,
            gamma=gamma,
            random_state=None,
            n_jobs=-1
        )
        spectral.fit(affinity_matrix)

        start_time = 0.0
        times = [(s.start + s.stop) / 2 for s in wav_splits]
        labelling = []
        prev_label = spectral.labels_[0]
        prev_time = start_time

        for i, time in enumerate(times):
            if i > 0 and spectral.labels_[i] != prev_label:
                start_time = prev_time / sampling_rate
                end_time = time / sampling_rate
                temp = ["Speaker " + str(prev_label+1), f"({start_time:.2f} - {end_time:.2f})"]
                labelling.append(tuple(temp))
                prev_time = time
            if i == len(times)-1:
                start_time = prev_time / sampling_rate
                end_time = (len(audio)) / 1000
                temp = ["Speaker " + str(spectral.labels_[i]+1), f"({start_time:.2f} - {end_time:.2f})"]
                labelling.append(tuple(temp))
            prev_label = spectral.labels_[i]


        model = Model("model/" + trans_model)
        wf = wave.open(filename, "rb")

        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)


        transcription = []
        while True:
            data = wf.readframes(16000)  # Read in chunks of 1 second
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                # Convert json output to dict
                result_dict = json.loads(rec.Result())
                # Extract start and end timestamps and text values
                start = result_dict["result"][0]["start"]
                end = result_dict["result"][-1]["end"]
                text = " ".join([word["word"] for word in result_dict["result"]])
                # Append dictionary to transcription list
                transcription.append({"start": start, "end": end, "text": text})

        # Sort transcription list by start time
        transcription = sorted(transcription, key=lambda x: x["start"])

        # Output the results in the format Speaker Number (Timestamp) : Transcription
        prev_end = 0
        for l, t in zip(labelling, transcription):
            start_time = str(timedelta(seconds=int(t["start"]))).split(".")[0]
            end_time = str(timedelta(seconds=int(t["end"]))).split(".")[0]
            if t["start"] > prev_end:
                trans = ("%s %s : \n%s \n" % (l[0], f"({start_time} - {end_time})", t["text"]))
            else:
                end_time = str(timedelta(seconds=int(prev_end))).split(".")[0]
                trans = ("%s %s :\n  %s \n" % (l[0], f"({end_time} - {end_time})", t["text"]))
            print(trans)
            self.ui.outputText.append(trans)
            prev_end = t["end"]

class SpeechLive(QThread):
    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.stop_recording = False


    def run(self):
       # Initialize PyAudio
        p = pyaudio.PyAudio()
        # Get list of available audio devices
        info = p.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        for i in range(0, numdevices):
                if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                    print("Input Device id ", i, " - ", p.get_device_info_by_host_api_device_index(0, i).get('name'))
                    self.ui.selectMicrophone.addItem(p.get_device_info_by_host_api_device_index(0, i).get('name'))

        # Select the microphone to use (you can change the device_index value as needed)
        device_index = 1
        print("Using device", p.get_device_info_by_index(device_index).get('name'))

        
        # Open audio stream from selected microphone
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8000, input_device_index=device_index)

        # Initialize Vosk model and recognizer
        # model = Model("vosk-model-en-us-aspire-0.2")
        selected_model = self.ui.selectLiveModel.currentText()

        if selected_model == "English 1" :
            trans_model = "vosk-model-en-us-0.22"
        elif selected_model == "English 2" :
            trans_model = "vosk-model-en-us-aspire-0.2"
        elif selected_model == "Filipino" :
            trans_model = "vosk-model-tl-ph-generic-0.6"


        model = Model("model/"+trans_model)
        rec = KaldiRecognizer(model, 16000)

        # Print message to indicate recording has started
        print("Recording started")
        self.ui.btnStopLive.setEnabled(True)
        self.ui.btnStopLive.setStyleSheet("background-color: red;")

        self.ui.btnStartLive.setEnabled(False)
        self.ui.btnStartLive.setStyleSheet("background-color: #024d00;")


        # Transcription list to store results
        transcription = []
        transcription_paragraphs = {}
        while not self.stop_recording:
            data = stream.read(16000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                # Convert json output to dict
                result_dict = json.loads(rec.Result())
                # Extract text value from the dict
                result_text = result_dict.get("text", "")
                # Print the result live on the console
                # words_spoken = (" "+result_text, end='', flush=True)
              
                # Append the result to the transcription list
                transcription.append(result_text)
                self.ui.outputText_Live.append(result_text)
            if self.stop_recording:
                break
        stream.stop_stream()
        stream.close()
        p.terminate()
              
    
    def stopRecording(self):
        print("Recording Stopped")
        self.stop_recording = True  # Set stop_recording flag variable to True when you want to stop the recording
        self.ui.btnStartLive.setEnabled(True)
        self.ui.btnStartLive.setStyleSheet("background-color: rgb(12, 149, 53);")
        self.ui.btnStartLive.setStyleSheet("color: white;")
        self.ui.btnStopLive.setEnabled(False)
        self.ui.btnStopLive.setStyleSheet("background-color: #834545;")


class Transcription(QThread):
    def __init__(self, ui, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.stop_recording = False


    def preprocess_audio(self, filename):
        # Check if the audio file is already in WAV format and is mono
        audio = AudioSegment.from_file(filename)
        if audio.channels != 1 or audio.sample_width != 2 or audio.frame_rate != 16000 or audio.sample_type != 'INT':
            # If it is not, convert it into a WAV mono file
            audio = AudioSegment.from_file(filename)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            filename = os.path.join(os.path.dirname(filename), f"{os.path.splitext(os.path.basename(filename))[0]}.wav")
            audio.export(filename, format='wav')
        elif os.path.splitext(filename)[1] == '.mp3':
            # If it is an MP3 file, convert it to WAV mono without using ffmpeg
            audio = AudioSegment.from_file(filename, format='mp3')
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            filename = os.path.join(os.path.dirname(filename), f"{os.path.splitext(os.path.basename(filename))[0]}.wav")
            audio.export(filename, format='wav')
        return filename


    def run(self):
       #get the selected model 
        selected_model = self.ui.selectModel.currentText()

        if selected_model == "English 1" :
            trans_model = "vosk-model-en-us-0.42-gigaspeech"
        elif selected_model == "English 2" :
            trans_model = "vosk-model-en-us-aspire-0.2"
        elif selected_model == "Filipino" :
            trans_model = "vosk-model-tl-ph-generic-0.6"

        # get the file
        filename = self.ui.uploadFilename.text()
        filename = self.preprocess_audio(filename)
        print(filename)
        print(trans_model)
        self.ui.consoleLog.append("> Transcription is Starting ")
        self.ui.consoleLog.append("> Model Selected:  "+trans_model)
        wf = wave.open(filename, "rb")

        

        model = Model("model/" + trans_model)
        rec = KaldiRecognizer(model, wf.getframerate())

        transcription = []



        #rec.SetWords(True)

        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                # Convert json output to dict
                result_dict = json.loads(rec.Result())
                # Extract text values and append them to transcription list
                transcription.append(result_dict.get("text", ""))

        # Get final bits of audio and flush the pipeline
        final_result = json.loads(rec.FinalResult())
        transcription.append(final_result.get("text", ""))
        # merge or join all list elements to one big string
        transcription_text = ' '.join(transcription)
        print(transcription_text)
        self.ui.outputText.append(transcription_text)
                
              
    

        

class UIS_RNN(MainWindow):
    def __init__(self):
        super().__init__()
        self.thread = None

    def transcribeAudio(self):
        self.thread = SpeechThread(self.ui)
        self.thread.start()

    def transcribeLiveStart(self):
        self.thread = SpeechLive(self.ui)
        self.thread.start()

    def stopLiveTranscription(self):
        if self.thread is not None and isinstance(self.thread, SpeechLive):
            self.thread.stopRecording()

    def transcribeOnly(self):
        self.thread = Transcription(self.ui)
        self.thread.start()


    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        super().closeEvent(event)

