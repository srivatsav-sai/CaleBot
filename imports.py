import nextcord as discord
import time
import re
import asyncio
import yt_dlp
import subprocess
import os
import configparser
import tempfile
import aiohttp

from pymongo import MongoClient
from nextcord.ext import application_checks, commands
from datetime import datetime, timedelta, timezone
from collections import deque
from pytube import Search
from bson import ObjectId