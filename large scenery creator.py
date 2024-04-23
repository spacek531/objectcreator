# made by spacek 2024-04-22

from PIL import Image
import numpy as np
import io
from os import mkdir, makedirs, replace
from shutil import copy, copyfile, make_archive, move, rmtree
import os
import sys
from json import load as jload
from json import dump as jdump
from enum import Enum
import os.path as ospath
from tempfile import TemporaryDirectory

from rctobject import constants as cts
from rctobject import objects as obj
from rctobject import palette as pal
from rctobject import sprites as spr

def tileOffsetToPixel(pos):
    return (-pos[1]+pos[0],(-pos[0]-pos[1])//2)

def rotate90(pos):
    return (pos[1],-pos[0])
def rotate180(pos):
    return (-pos[0],-pos[1])
def rotate270(pos):
    return (-pos[1],pos[0])
rotatefuncs = [lambda x: x, rotate90, rotate180, rotate270]

"""
WALLS AND CORNERS

Walls property are the sides you are allowed to place walls on
Corners property are the quarter tile segments that the large scenery occupies
They are 4-bit values

You can orient yourself ingame with the 3D sign or Six Flag sign objects.
The sign will be in on the northeast side, facing southwest. This is the default orientation.
                         ^
                    8  /   \  1
                      /\ 4 /\
                     < 2 x 8 >
                      \/ 1 \/
                    4  \   /  2
                         v
Northeast wall is bit 1     South quadrant is bit 1
Southeast wall is bit 2      West quadrant is bit 2
Southwest wall is bit 4     North quadrant is bit 4
Northwest wall is bit 8      East quadrant is bit 8
"""
# OpenRCT2 draws thumbnails positioned at the top center of the box
thumbnailSize = (64, 78)
def getThumbnailOffset(imageSize):
    return ((-imageSize[0])//2, (thumbnailSize[1] - imageSize[1])//2)

def BuildScenery(jsonfilepath, exportPath, exportMode):
    # open the object
    jsondir = ospath.dirname(ospath.abspath(jsonfilepath))
    filename, extension = ospath.splitext(jsonfilepath)
    if extension.lower() != ".json":
        print("Expects a json input file. Input file was '"+jsonfilepath+"'")
        return
    print(f"loading file '{jsonfilepath}'")
    data = jload(fp=open(jsonfilepath, encoding='utf8'))
    filename = data["id"]
    print("filename is",filename)
    # collect image manifest from object file
    importImageData = data.get('importImages')
    imageManifest = None
    selectedColors = None
    imageBasePath = None
    resizeThumbnail = True
    smallestResizePercent = None
    recolorTo = "NoColor"
    if importImageData:
        selectedColors = importImageData.get('importSelectedColors')
        recolorTo = importImageData.get('recolorTo')
        imageManifest = importImageData.get('images')
        imageBasePath = importImageData.get('imageBasePath')
        resizeThumbnail = importImageData.get('resizeThumbnail',True)
        smallestResizePercent = importImageData.get('resizePercent')
    else:
        print("Expects 'importImages' object in the json root object. Doing no work.")
        return
    del(data["importImages"])
    
    if type(imageManifest) is not list:
        print("Expects 'images' array in 'importImages' object. Doing no work.")
    if type(imageBasePath) is str:
        imageManifest = [ ospath.abspath(ospath.join(jsondir,ospath.join(imageBasePath, relpath))) for relpath in imageManifest]
    else:
        imageManifest = [ospath.abspath(ospath.join(jsondir, relpath)) for relpath in imageManifest]
    
    # import images from image manifest
    data["images"] = []
    sprites = []
    exportImageIndex = 0
    importImageIndex = 0
    imageListLength = len(imageManifest)
    tileIndex = 0
    imageFailure = False
    # import thumbnails
    for i in range(importImageIndex, importImageIndex + 4):
            try:
                sprite = spr.Sprite.fromFile(path = imageManifest[i], selected_colors = selectedColors)
                sprite.colorAllInRemap(color_name = recolorTo)
                thumbOffset = getThumbnailOffset(sprite.image.size)
                sprites.append(sprite)
                data["images"].append({"x": thumbOffset[0], "y":thumbOffset[1],"path":f'images/thumb_{i-importImageIndex}.png'})
                print("Loaded thumbnail image '"+imageManifest[importImageIndex]+"'",sprite.image.size,"with sprite offset",thumbOffset)
            except Exception as e:
                print("Error loading thumbnail image '"+imageManifest[importImageIndex]+"': "+str(e))
                imageFailure = True
    if imageFailure:
        print("Images loaded incorrectly. Quitting.")
        return
    # Resize thumbnails to fit
    if resizeThumbnail:
        if not smallestResizePercent:
            smallestResizePercent = 1
            for i in range(exportImageIndex, exportImageIndex + 4):
                smallestResizePercent = min(smallestResizePercent,thumbnailSize[0]/sprites[i].image.size[0])
                smallestResizePercent = min(smallestResizePercent,thumbnailSize[1]/sprites[i].image.size[1])
        else:
            smallestResizePercent /= 100
        print(f"Scaling thumbnails to {smallestResizePercent * 100}%")
        for i in range(exportImageIndex, exportImageIndex + 4):
            sprite = sprites[i]
            entry = data["images"][i]
            sprite.image.thumbnail((sprite.image.size[0]*smallestResizePercent,sprite.image.size[1]*smallestResizePercent), Image.NEAREST)
            offset = getThumbnailOffset((sprite.image.size[0],sprite.image.size[1]))
            entry["x"] = offset[0]
            entry["y"] = offset[1]
    importImageIndex += 4
    exportImageIndex += 4
    
    #import tile images
    for tile in data["properties"]["tiles"]:
        print(f"loading images for tile {tileIndex}. Coordinates {tile['x']},{tile['y']}")
        for i in range(4):
            try:
                rotatedCoords = rotatefuncs[i]((tile["x"], tile["y"]))
                pixelOffset = tileOffsetToPixel(rotatedCoords)
                sprite = spr.Sprite.fromFile(path = imageManifest[importImageIndex], selected_colors = selectedColors)
                sprite.colorAllInRemap(color_name = recolorTo)
                data["images"].append({"x": sprite.x+pixelOffset[0], "y":sprite.y+pixelOffset[1]+15,"path":f'images/tile_{tileIndex}_im_{i}.png'})
                sprites.append(sprite)
                print("Loaded tile image '"+imageManifest[importImageIndex]+"'",sprite.image.size,"with sprite offset",(data["images"][-1]["x"],data["images"][-1]["y"]))
            except Exception as e:
                print("Error loading thumbnail image '"+imageManifest[importImageIndex]+"': "+str(e))
                imageFailure = True
            importImageIndex += 1
            exportImageIndex += 1
        tileIndex += 1
    if imageFailure:
        print("Images loaded incorrectly. Quitting.")
        return

    if exportMode == "no-export":
        print("no-export flag passed. Quitting.")
        return
    # compile parkobj
    with TemporaryDirectory() as temp:
        tempPath = str(temp)
        print("Created temporary directory for compiling data",tempPath)
        tempImages = tempPath+"/images"
        mkdir(f'{tempImages}')
        for i in range(len(data["images"])):
            sprites[i].save(ospath.join(tempPath,data["images"][i]["path"]))
            print("saved image",ospath.join(tempPath,data["images"][i]["path"]))
        with open(ospath.join(tempPath,"object.json"), mode='w') as file:
            jdump(obj=data, fp=file, indent=2)
            print("saved configuration",ospath.join(tempPath,"object.json"))
        
        # write unzipped
        if exportMode in exportFolder:
            finalPath = ospath.join(exportPath,filename)
            if exportMode in exportAbs:
                finalPath = exportPath
            rmtree(finalPath, ignore_errors = True)
            makedirs(finalPath, exist_ok = True)
            move(tempImages,finalPath)
            move(ospath.join(tempPath,"object.json"),ospath.join(finalPath,"object.json"))
            print("Unzipped object moved to",finalPath)
            return
        
        #write zipped
        finalPath = ospath.join(exportPath, filename)
        if exportMode in exportAbs:
            finalPath = exportPath
        print(exportPath, filename, finalPath)
        zipCreated = make_archive(base_name = finalPath, root_dir = temp, format = "zip")
        replace(finalPath+".zip",finalPath+".parkobj")
        print("Parkobj moved to",finalPath+".parkobj")

commandKeywords = {
    "unzip-abs": 1,
    "unzip":1,
    "parkobj-abs":1,
    "parkobj":1,
    "no-export":0
}
exportAbs = { "unzip-abs","parkobj-abs"}
exportFolder = {"unzip","unzip-abs"}

def main(argv):
    print("Large Scenery Creator script by Spacek")
    if len(argv)< 2 or argv[1] in ["h", "help","-h","--h"]:
        print("""Usage:
    scriptfile.py <input jsons> ... [options] ...

optional arguments:
    --unzip-abs <path to directory to put object directory>
    --unzip <path to directory to put object directory, automatic folder name>
    --parkobj-abs <path to file output>
    --parkobj <path to directory to put parkobj, automatic file name>
    --no-export
default behavior:
    scriptfile.py <input json> --parkobj-dir "D:/Documents/OpenRCT2/object\"""")
        return
    # command line arguments
    exportPath = "D:/Documents/OpenRCT2/object"
    exportMode = "parkobj"
    
    for flag in commandKeywords.keys():
        if "--"+flag in argv:
            exportMode = flag
            exportPath = argv[argv.index("--"+flag)+commandKeywords[flag]]
    
    print("exportMode:",exportMode,"exportPath:",exportPath)

    for i in range(1, len(argv)):
        if argv[i][2:] in commandKeywords:
            break
        BuildScenery(argv[i], exportPath, exportMode)

if __name__ == "__main__":
    main(sys.argv)