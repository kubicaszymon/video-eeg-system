These steps worked for me using GIMP 2.8.10:

    create an image using RGB mode (Image > Mode > RGB) using the appropriate size for whatever you are creating (164x314 for MUI_WELCOMEFINISHPAGE_BITMAP, 150x57 for MUI_HEADERIMAGE_BITMAP)
    File > Export as ...
    name your file with a .bmp extension
    click "Export"
    in the window titled "Export Image as BMP" expand "Compatibility Options" and check the box that says "Do not write color space information"
    also, in the window titled "Export Image as BMP" expand "Advanced Options" and check the radio button under "24 bits" next to "R8 G8 B8"
    click "Export"
