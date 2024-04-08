import nextcord as discord
import time
import re
import yt_dlp as youtube_dl
import json
import requests
import asyncio
import logging
import collections
import urllib
import os
from pymongo import MongoClient
from nextcord.ext import application_checks
from nextcord.ext import commands
from datetime import datetime, timedelta, timezone
from yt_dlp import YoutubeDL
from nextcord import FFmpegOpusAudio
from collections import deque
from pytube import YouTube, Search
