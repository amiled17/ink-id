import numpy as np
from PIL import Image
import cv2
import os
import re
import pdb

dataPath = "/home/volcart/volumes/packages/CarbonPhantom-Feb2017.volpkg/paths/20170221130948/layered/resliced/"
dataFiles = os.listdir(dataPath)
dataFiles.sort(key=lambda var:[int(x) if x.isdigit() else x for x in re.findall(r'[^0-9]|[0-9]+', var)])

volume = []
for f in dataFiles:
    sliceData = np.array(Image.open(dataPath+f))
    volume.append(sliceData)
volume = np.transpose(volume, (2,1,0))

xCoordinates = [3650,4300]
yCoordinates = [450,1930]
zCoordinates = [0,volume.shape[2]]

newVolume = volume[xCoordinates[0]:xCoordinates[1], yCoordinates[0]:yCoordinates[1], zCoordinates[0]:zCoordinates[1]]

slicesPath = "/home/volcart/volumes/packages/CarbonPhantom-Feb2017.volpkg/paths/20170221130948/layered/column-6/"
for i in range(newVolume.shape[2]):
    predictionSlice = 255 * (newVolume[:,:,i] - np.min(newVolume)) / (np.amax(newVolume) - np.min(newVolume))
    sliceNumber = str(i).zfill(4)
    cv2.imwrite(slicesPath+"/"+str(sliceNumber)+".png", predictionSlice)
