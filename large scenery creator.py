# made by spacek 2024-04-22

commandKeywords = {
    "unzip-abs": 1,
    "unzip-dir": 1,
    "unzip":1,
    "parkobj-abs":1,
    "parkobj-dir":1,
    "parkobj":1,
    "no-export":0
}
exportAbs = { "unzip-abs","parkobj-abs"}
exportFolder = {"unzip","unzip-abs","unzip-dir"}

from PIL import Image
import numpy as np
import io
from os import mkdir, makedirs, replace, walk
from shutil import copy, copyfile, make_archive, move, rmtree
import os
import sys
from json import load as jload
from json import dump as jdump
from enum import Enum
import os.path as ospath
from tempfile import TemporaryDirectory
import unicodedata

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

printable_characters = []
characterMap = [0 for _ in range(256)]

for i in range(256):
    try:
        charname = unicodedata.name(chr(i))
        printable_characters.append(i)
        characterMap[i] = len(printable_characters) - 1
    except:
        characterMap[i] = 0

characterWidthOverride = {
    32: 5,
}

def spriteIsEmpty(sprite):
    extrema = sprite.image.getextrema()
    if extrema[0] == (0,0) and extrema[1] == (0,0) and extrema[2] == (0,0) and extrema[3] == (0,0):
        return True
    return False

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
    selectedColorsThumbnail = None
    
    resizeThumbnail = True
    smallestResizePercent = None
    recolorTo = False
    recolorThumbnailTo = False
    
    sign3DRecolorTo = False
    sign3DSelectedColors = None
    useSign3D = "3dFont" in data["properties"]
    sign3DImagesMap = [0, 1, 2, 3] # maps rotations to sprites
    sign3DImportIncrement = 4 # how many images to import for each character
    sign3DExportIncrement = 4 # how many images to export for each character
    sign3DDefaultGlyph = {"width": 8, "height": 10, "image": 0}
    sign3DWidthOffset = 0 # character width is image width plus this
    sign3DSpecificOffsets = {}
    sign3DIncludeGlyphName = False # put the glyph name in the object json
    sign3D = None
    if useSign3D:
        sign3D = data["properties"]["3dFont"]
    sign3DImagesBasePath = None # directory that sprite files are in
    sign3DImageName = None # filename with c-type number format
    sign3DStartCharacter = 32 # character of source image 0
    
    if importImageData:
        selectedColors = importImageData.get('importSelectedColors')
        recolorTo = importImageData.get('recolorTo')
        recolorThumbnailTo = importImageData.get('recolorThumbnailTo', recolorTo)
        imageManifest = importImageData.get('images')
        imageBasePath = importImageData.get('imageBasePath')
        selectedColorsThumbnail = importImageData.get('selectedColorsThumbnail', selectedColors)
        sign3DProperties = importImageData.get("3dFont")
        if sign3DProperties:
            sign3DRecolorTo = sign3DProperties.get('recolorTo')
            sign3DSelectedColors = sign3DProperties.get('importSelectedColors')
            sign3DImagesBasePath = sign3DProperties.get('imageBasePath')
            sign3DImageName = sign3DProperties.get('imageName')
            sign3DImagesMap = sign3DProperties.get('imagesMap',sign3DImagesMap)
            sign3DWidthOffset = sign3DProperties.get('widthOffset', sign3DWidthOffset)
            sign3DDefaultGlyph["width"] = sign3DProperties.get('defaultCharacterHeight', sign3DDefaultGlyph["width"])
            sign3DDefaultGlyph["height"] = sign3DProperties.get('defaultCharacterWidth', sign3DDefaultGlyph["height"])
            sign3DImportIncrement = sign3DProperties.get('importIncrement',max(sign3DImagesMap)+1)
            sign3DExportIncrement = sign3DProperties.get('exportIncrement',sign3DExportIncrement)
            sign3DIncludeGlyphName = sign3DProperties.get('includeGlyphName',sign3DIncludeGlyphName)
            sign3DStartCharacter = sign3DProperties.get('startCharacter',sign3DStartCharacter)
            sign3DSpecificOffsets = sign3DProperties.get('specificOffsets',{})
            if type(sign3DStartCharacter) == str:
                sign3DStartCharacter = ord(sign3DStartCharacter)
        elif useSign3D:
            print("3dFont defined in object properties but 3dFont missing from importImages. Quitting.")
            return
        if type(imageManifest) is not list:
            print("Expects 'images' array in 'importImages' object. Quitting.")
            return
        
        if type(imageBasePath) is str:
            imageManifest = [ ospath.abspath(ospath.join(jsondir,ospath.join(imageBasePath, relpath))) for relpath in imageManifest]
        else:
            imageManifest = [ospath.abspath(ospath.join(jsondir, relpath)) for relpath in imageManifest]
        
        resizeThumbnail = importImageData.get('resizeThumbnail',True)
        smallestResizePercent = importImageData.get('resizePercent')
    else:
        print("Expects 'importImages' object in the json root object. Quitting.")
        return
    del(data["importImages"])
    
    # import images from image manifest
    images = [] # entries in the images array
    sprites = [] # pixel data
    exportImageIndex = 0
    exportSpriteIndex = 0
    importImageIndex = 0
    imageListLength = len(imageManifest)
    tileIndex = 0
    imageFailure = False

    #import 3D sign images
    if useSign3D:
        print("Adding 3D sign")
        print("sign3DImagesMap is",sign3DImagesMap)
        print("sign3DImportIncrement is",sign3DImportIncrement)
        print("sign3DExportIncrement is",sign3DExportIncrement)
        print("sign3DDefaultGlpyh is",sign3DDefaultGlyph)
        numImages = 0
        glyphs = []
        # non-printable character
        for _ in range(sign3DExportIncrement):
            images.append("")
            exportImageIndex += 1
        numImages += 1
        
        if not ospath.exists(sign3DImagesBasePath):
            print("this path does not exist:",sign3DImagesBasePath,"Quitting.")
            return
        imageFiles = next(walk(sign3DImagesBasePath), (None, None, []))[2]
        if len(imageFiles) == 0:
            print("Could not find any files in directory",sign3DImagesBasePath,"Quitting.")
            return
        imageImportStatus = [ None for _ in range(len(printable_characters) * sign3DImportIncrement)] # if the sprites imported correctly
        for i in range(len(imageImportStatus)):
            imageName = sign3DImageName % i
            if imageName in imageFiles:
                #try:
                charpath = ospath.join(sign3DImagesBasePath, imageName)
                sprite = spr.Sprite.fromFile(path = charpath, selected_colors = selectedColors)
                if spriteIsEmpty(sprite):
                    print("empty image",charpath)
                    continue
                if sign3DRecolorTo:
                    sprite.colorAllInRemap(color_name = sign3DRecolorTo)
                sprite.outputPath = f"images/char_{i}.png"
                imageImportStatus[i] = len(sprites)
                sprites.append(sprite)
                exportSpriteIndex += 1
                print("Loaded character image '"+charpath+"'",sprite.image.size,"with sprite offset",(sprite.x, sprite.y),"as sprite",len(sprites)-1)
                #except Exception as e:
                #    print("Error loading character image '"+charpath+"': "+str(e))
                #    imageFailure = True
            if imageFailure:
                print("Images loaded incorrectly. Quitting.")
                return
        
        # determine how many characters imported successfully and update the map
        characterImages = [None for _ in range(len(printable_characters))]
        for i in range(len(printable_characters)):
            myImages = imageImportStatus[i*sign3DImportIncrement:(i+1)*sign3DImportIncrement]
            if myImages.count(None) == sign3DImportIncrement:
                print("No images for character",printable_characters[i])
                continue
            for index in sign3DImagesMap:
                if myImages[index] == None:
                    images.append("")
                else:
                    sprite = sprites[myImages[index]]
                    images.append({"x":sprite.x, "y":sprite.y, "sprite":myImages[index]})
                exportImageIndex += 1
            print("Printable character ",chr(printable_characters[i]),printable_characters[i],"mapped to",myImages)
            characterImages[i] ={"image": numImages, "images": images[-sign3DExportIncrement:]}
            numImages += 1
        
        # map codepoints to characters
        for i in range(len(characterMap)):
            glyph = dict(sign3DDefaultGlyph)
            if sign3DIncludeGlyphName:
                glyph["name"] = i
            #print("character",i,"maps to image",mappedImage)
            if i in printable_characters:
                print("character is printable:",i, chr(i))
                characterImage = characterImages[printable_characters.index(i)]
                if characterImage == None:
                    print("printable character",chr(i),i, "has no associated sprite")
                    glyphs.append(glyph)
                    continue
                if sign3DIncludeGlyphName:
                    glyph["name"] = unicodedata.name(chr(i))
                    glyph["number"] = i
                characterWidth = 0
                for image in characterImage["images"]:
                    if type(image)==str:
                        glyphs.append(glyph)
                        continue
                    characterWidth = max(characterWidth, sprites[image["sprite"]].image.size[0])
                characterWidth += sign3DWidthOffset
                if chr(i) in sign3DSpecificOffsets:
                    characterWidth += sign3DSpecificOffsets[chr(i)]
                elif i in sign3DSpecificOffsets:
                    characterWidth += sign3DSpecificOffsets[i]
                #print("Width of",unicodedata.name(chr(i)),"is",characterWidth)
                glyph["width"] = characterWidth
                glyph["image"] = characterImage["image"]
            glyphs.append(glyph)
        
        sign3D["numImages"] = numImages
        sign3D["glyphs"] = glyphs
    # import thumbnails
    for i in range(importImageIndex, importImageIndex + 4):
            try:
                sprite = spr.Sprite.fromFile(path = imageManifest[i], selected_colors = selectedColorsThumbnail)
                if recolorThumbnailTo:
                    sprite.colorAllInRemap(color_name = thumbnailRemapTo)
                thumbOffset = getThumbnailOffset(sprite.image.size)
                sprite.outputPath = f'images/thumb_{i - importImageIndex}.png'
                images.append({"x": thumbOffset[0], "y":thumbOffset[1],"sprite": len(sprites)})
                sprites.append(sprite)
                print("Loaded thumbnail image '"+imageManifest[importImageIndex + i]+"'",sprite.image.size,"with sprite offset",thumbOffset,"as sprite",len(sprites)-1)
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
            for i in range(exportSpriteIndex, exportSpriteIndex + 4):
                smallestResizePercent = min(smallestResizePercent,thumbnailSize[0]/sprites[i].image.size[0])
                smallestResizePercent = min(smallestResizePercent,thumbnailSize[1]/sprites[i].image.size[1])
        else:
            smallestResizePercent /= 100
        print(f"Scaling thumbnails to {smallestResizePercent * 100}%")
        for i in range(4):
            sprite = sprites[exportSpriteIndex + i]
            entry = images[exportImageIndex + i]
            sprite.image.thumbnail((sprite.image.size[0]*smallestResizePercent,sprite.image.size[1]*smallestResizePercent), Image.NEAREST)
            offset = getThumbnailOffset((sprite.image.size[0],sprite.image.size[1]))
            entry["x"] = offset[0]
            entry["y"] = offset[1]
    importImageIndex += 4
    exportSpriteIndex += 4
    exportImageIndex += 4
    
    #import tile images
    for tile in data["properties"]["tiles"]:
        print(f"loading images for tile {tileIndex}. Coordinates {tile['x']},{tile['y']}")
        for i in range(4):
            try:
                rotatedCoords = rotatefuncs[i]((tile["x"], tile["y"]))
                pixelOffset = tileOffsetToPixel(rotatedCoords)
                sprite = spr.Sprite.fromFile(path = imageManifest[importImageIndex], selected_colors = selectedColors)
                if recolorTo:
                    sprite.colorAllInRemap(color_name = recolorTo)
                sprite.outputPath = f'images/tile_{tileIndex}_im_{i}.png'
                images.append({"x": sprite.x+pixelOffset[0], "y":sprite.y+pixelOffset[1]+15,"sprite":len(sprites)})
                sprites.append(sprite)
                print("Loaded tile image '"+imageManifest[importImageIndex]+"'",sprite.image.size,"with sprite offset",(images[-1]["x"],images[-1]["y"]),"as sprite",len(sprites)-1)
            except Exception as e:
                print("Error loading thumbnail image '"+imageManifest[importImageIndex]+"': "+str(e))
                imageFailure = True
            importImageIndex += 1
            exportImageIndex += 1
            exportSpriteIndex += 1
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
        for sprite in sprites:
            sprite.save(ospath.join(tempPath,sprite.outputPath))
            print("saved image",ospath.join(tempPath,sprite.outputPath))
        for image in images:
            if type(image) == dict:
                image["path"] = sprites[image["sprite"]].outputPath
                del(image["sprite"])
        data["images"] = images
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