# -*- coding: utf-8 -*-
"""
Created on Fri Jul 15 12:25:40 2016

@author: Luciano Masullo, Federico Barabas
"""

import os
import time
import math
import numpy as np
from scipy import ndimage as ndi
import tifffile as tiff
from PIL import Image
import matplotlib.pyplot as plt
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore

import labnanofisica.utils as utils
import labnanofisica.ringfinder.tools as tools


class Gollum(QtGui.QMainWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.i = 0

        self.setWindowTitle('Gollum: the Ring Finder')

        self.cwidget = QtGui.QWidget()
        self.setCentralWidget(self.cwidget)

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&Run')
        batchSTORMAct = QtGui.QAction('Analyze batch of STORM images...', self)
        batchSTEDAct = QtGui.QAction('Analyze batch of STED images...', self)
        batchSTORMAct.triggered.connect(self.batchSTORM)
        batchSTEDAct.triggered.connect(self.batchSTED)
        fileMenu.addAction(batchSTORMAct)
        fileMenu.addAction(batchSTEDAct)
        fileMenu.addSeparator()

        exitAction = QtGui.QAction(QtGui.QIcon('exit.png'), '&Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(QtGui.QApplication.closeAllWindows)
        fileMenu.addAction(exitAction)

        self.folderStatus = QtGui.QLabel('Ready', self)
        self.statusBar().addPermanentWidget(self.folderStatus, 1)
        self.fileStatus = QtGui.QLabel('Ready', self)
        self.statusBar().addPermanentWidget(self.fileStatus)

        # Main Widgets' layout
        self.mainLayout = QtGui.QGridLayout()
        self.cwidget.setLayout(self.mainLayout)

        # Image with correlation results
        self.corrImgWidget = pg.GraphicsLayoutWidget()
        self.corrImgItem = pg.ImageItem()
        self.corrVb = self.corrImgWidget.addViewBox(col=0, row=0)
        self.corrVb.setAspectLocked(True)
        self.corrVb.addItem(self.corrImgItem)
        self.corrImgHist = pg.HistogramLUTItem()
        self.corrImgHist.gradient.loadPreset('thermal')
        self.corrImgHist.setImageItem(self.corrImgItem)
        self.corrImgHist.vb.setLimits(yMin=0, yMax=20000)
        self.corrImgWidget.addItem(self.corrImgHist)
        self.corrResult = pg.ImageItem()
        self.corrVb.addItem(self.corrResult)

        # Image with ring results
        self.ringImgWidget = pg.GraphicsLayoutWidget()
        self.ringImgItem = pg.ImageItem()
        self.ringVb = self.ringImgWidget.addViewBox(col=0, row=0)
        self.ringVb.setAspectLocked(True)
        self.ringVb.addItem(self.ringImgItem)
        self.ringImgHist = pg.HistogramLUTItem()
        self.ringImgHist.gradient.loadPreset('thermal')
        self.ringImgHist.setImageItem(self.ringImgItem)
        self.ringImgHist.vb.setLimits(yMin=0, yMax=20000)
        self.ringImgWidget.addItem(self.ringImgHist)
        self.ringResult = pg.ImageItem()
        self.ringVb.addItem(self.ringResult)

        # Separate frame for loading controls
        loadFrame = QtGui.QFrame(self)
        loadFrame.setFrameStyle(QtGui.QFrame.Panel)
        loadLayout = QtGui.QGridLayout()
        loadFrame.setLayout(loadLayout)
        loadTitle = QtGui.QLabel('<strong>Load image</strong>')
        loadTitle.setTextFormat(QtCore.Qt.RichText)
        loadLayout.addWidget(loadTitle, 0, 0, 1, 2)
        loadLayout.addWidget(QtGui.QLabel('STORM pixel [nm]'), 1, 0)
        self.STORMPxEdit = QtGui.QLineEdit()
        loadLayout.addWidget(self.STORMPxEdit, 1, 1)
        loadLayout.addWidget(QtGui.QLabel('STORM magnification'), 2, 0)
        self.magnificationEdit = QtGui.QLineEdit()
        loadLayout.addWidget(self.magnificationEdit, 2, 1)
        self.loadSTORMButton = QtGui.QPushButton('Load STORM Image')
        loadLayout.addWidget(self.loadSTORMButton, 3, 0, 1, 2)
        loadLayout.addWidget(QtGui.QLabel('STED pixel [nm]'), 4, 0)
        self.STEDPxEdit = QtGui.QLineEdit()
        loadLayout.addWidget(self.STEDPxEdit, 4, 1)
        self.loadSTEDButton = QtGui.QPushButton('Load STED Image')
        loadLayout.addWidget(self.loadSTEDButton, 5, 0, 1, 2)
        loadLayout.setColumnMinimumWidth(1, 40)
        loadFrame.setFixedHeight(180)

        # Ring finding method settings frame
        self.intThrLabel = QtGui.QLabel('#sigmas threshold from mean')
        self.intThresEdit = QtGui.QLineEdit()
        self.sigmaEdit = QtGui.QLineEdit()
        self.lineLengthEdit = QtGui.QLineEdit()
        self.roiSizeEdit = QtGui.QLineEdit()
        self.corrThresEdit = QtGui.QLineEdit('0')
        self.corrSlider = QtGui.QSlider(QtCore.Qt.Horizontal, self)
        self.corrSlider.setMinimum(0)
        self.corrSlider.setMaximum(250)   # Divide by 1000 to get corr value
        self.corrSlider.setValue(1000*float(self.corrThresEdit.text()))
        self.corrSlider.valueChanged[int].connect(self.sliderChange)
        self.showCorrMapCheck = QtGui.QCheckBox('Show correlation map', self)
        self.thetaStepEdit = QtGui.QLineEdit()
        self.deltaThEdit = QtGui.QLineEdit()
        self.sinPowerEdit = QtGui.QLineEdit()
        self.corrButton = QtGui.QPushButton('Run analysis')
        self.corrButton.setCheckable(True)
        settingsFrame = QtGui.QFrame(self)
        settingsFrame.setFrameStyle(QtGui.QFrame.Panel)
        settingsLayout = QtGui.QGridLayout()
        settingsFrame.setLayout(settingsLayout)
        settingsTitle = QtGui.QLabel('<strong>Ring finding settings</strong>')
        settingsTitle.setTextFormat(QtCore.Qt.RichText)
        settingsLayout.addWidget(settingsTitle, 0, 0, 1, 2)
        wvlenLabel = QtGui.QLabel('Rings periodicity [nm]')
        self.wvlenEdit = QtGui.QLineEdit()
        settingsLayout.addWidget(wvlenLabel, 1, 0)
        settingsLayout.addWidget(self.wvlenEdit, 1, 1)
        corrThresLabel = QtGui.QLabel('Discrimination threshold')
        settingsLayout.addWidget(corrThresLabel, 2, 0)
        settingsLayout.addWidget(self.corrThresEdit, 2, 1)
        settingsLayout.addWidget(self.corrSlider, 3, 0, 1, 2)
        settingsLayout.addWidget(self.showCorrMapCheck, 4, 0, 1, 2)
        settingsLayout.addWidget(self.corrButton, 5, 0, 1, 2)
        loadLayout.setColumnMinimumWidth(1, 40)
        settingsFrame.setFixedHeight(180)

        # Load settings configuration and then connect the update
        try:
            tools.loadConfig(self)
        except:
            tools.saveDefaultConfig()
            tools.loadConfig(self)
        self.STORMPxEdit.editingFinished.connect(self.updateConfig)
        self.magnificationEdit.editingFinished.connect(self.updateConfig)
        self.STEDPxEdit.editingFinished.connect(self.updateConfig)
        self.roiSizeEdit.editingFinished.connect(self.updateConfig)
        self.sigmaEdit.editingFinished.connect(self.updateConfig)
        self.intThresEdit.editingFinished.connect(self.updateConfig)
        self.lineLengthEdit.editingFinished.connect(self.updateConfig)
        self.wvlenEdit.editingFinished.connect(self.updateConfig)
        self.sinPowerEdit.editingFinished.connect(self.updateConfig)
        self.thetaStepEdit.editingFinished.connect(self.updateConfig)
        self.deltaThEdit.editingFinished.connect(self.updateConfig)
        self.corrThresEdit.editingFinished.connect(self.updateConfig)

        self.buttonWidget = QtGui.QWidget()
        buttonsLayout = QtGui.QGridLayout()
        self.buttonWidget.setLayout(buttonsLayout)
        buttonsLayout.addWidget(loadFrame, 0, 0)
        buttonsLayout.addWidget(settingsFrame, 1, 0)

        # layout of the three widgets
        self.mainLayout.addWidget(self.buttonWidget, 1, 0)
        corrLabel = QtGui.QLabel('Correlation')
        corrLabel.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.mainLayout.addWidget(corrLabel, 0, 1)
        self.mainLayout.addWidget(self.corrImgWidget, 1, 1, 2, 1)
        ringLabel = QtGui.QLabel('Rings')
        ringLabel.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.mainLayout.addWidget(ringLabel, 0, 2)
        self.mainLayout.addWidget(self.ringImgWidget, 1, 2, 2, 1)
        self.mainLayout.setColumnMinimumWidth(1, 600)
        self.mainLayout.setColumnMinimumWidth(2, 600)
        self.buttonWidget.setFixedWidth(200)

        self.loadSTORMButton.clicked.connect(self.loadSTORM)
        self.loadSTEDButton.clicked.connect(self.loadSTED)
        self.sigmaEdit.textChanged.connect(self.updateImage)
        self.corrButton.clicked.connect(self.ringFinder)

        # Load sample STED image
        folder = os.path.join(os.getcwd(), 'labnanofisica', 'ringfinder')
        if os.path.exists(folder):
            self.loadSTED(os.path.join(folder, 'spectrinSTED.tif'))
        else:
            self.loadSTED(os.path.join(os.getcwd(), 'spectrinSTED.tif'))

    def updateConfig(self):
        tools.saveConfig(self)

    def sliderChange(self, value):
        self.corrThresEdit.setText(str(np.round(0.001*value, 2)))
        self.corrEditChange(str(value/1000))

    def corrEditChange(self, text):
        self.corrSlider.setValue(1000*float(text))
        if self.analyzed:
            self.corrThres = float(text)
            self.ringsBig = np.nan_to_num(self.localCorrBig) > self.corrThres
            self.ringsBig = self.ringsBig.astype(float)
            self.ringResult.setImage(np.fliplr(np.transpose(self.ringsBig)))

    def loadSTED(self, filename=None):
        load = self.loadImage(np.float(self.STEDPxEdit.text()), 'STED',
                              filename=filename)
        if load:
            self.sigmaEdit.setText('100')
            self.intThresEdit.setText('0.5')

    def loadSTORM(self, filename=None):
        # The STORM image has black borders because it's not possible to
        # localize molecules near the edge of the widefield image.
        # Therefore we need to crop those 3px borders before running the
        # analysis.
        mag = np.float(self.magnificationEdit.text())
        load = self.loadImage(np.float(self.STORMPxEdit.text()), 'STORM',
                              crop=int(3*mag), filename=filename)
        if load:
            self.corrImgHist.setLevels(0, 3)
            self.ringImgHist.setLevels(0, 3)
            self.sigmaEdit.setText('100')
            self.intThresEdit.setText('0.5')

    def loadImage(self, pxSize, tt, crop=0, filename=None):

        try:

            if not(isinstance(filename, str)):
                self.filename = utils.getFilename('Load ' + tt + ' image',
                                                  [('Tiff file', '.tif')],
                                                  os.getcwd())
            else:
                self.filename = filename

            if self.filename is not None:

                self.corrButton.setChecked(False)
                self.analyzed = False

                self.initialdir = os.path.split(self.filename)[0]
                self.crop = np.int(crop)
                self.pxSize = pxSize
                self.corrVb.clear()
                self.corrResult.clear()
                self.ringVb.clear()
                self.ringResult.clear()

                im = Image.open(self.filename)
                self.inputData = np.array(im).astype(np.float64)
                self.initShape = self.inputData.shape
                bound = (np.array(self.initShape) - self.crop).astype(np.int)
                self.inputData = self.inputData[self.crop:bound[0],
                                                self.crop:bound[1]]
                self.shape = self.inputData.shape
                self.updateImage()
                self.corrVb.addItem(self.corrImgItem)
                self.ringVb.addItem(self.ringImgItem)
                showIm = np.fliplr(np.transpose(self.inputData))
                self.corrImgItem.setImage(showIm)
                self.ringImgItem.setImage(showIm)

                # We need 1um n-sized subimages
                self.subimgPxSize = 1000/self.pxSize
                self.n = (np.array(self.shape)/self.subimgPxSize).astype(int)
                self.grid = tools.Grid(self.corrVb, self.shape, self.n)

                self.corrVb.setLimits(xMin=-0.05*self.shape[0],
                                      xMax=1.05*self.shape[0], minXRange=4,
                                      yMin=-0.05*self.shape[1],
                                      yMax=1.05*self.shape[1], minYRange=4)
                self.ringVb.setLimits(xMin=-0.05*self.shape[0],
                                      xMax=1.05*self.shape[0], minXRange=4,
                                      yMin=-0.05*self.shape[1],
                                      yMax=1.05*self.shape[1], minYRange=4)

                self.dataMean = np.mean(self.inputData)
                self.dataStd = np.std(self.inputData)

                self.corrVb.addItem(self.corrResult)
                self.ringVb.addItem(self.ringResult)

                return True

            else:
                return False

        except OSError:
            self.fileStatus.setText('No file selected!')

    def updateImage(self):
        self.gaussSigma = np.float(self.sigmaEdit.text())/self.pxSize
        self.inputDataS = ndi.gaussian_filter(self.inputData,
                                              self.gaussSigma)
        self.meanS = np.mean(self.inputDataS)
        self.stdS = np.std(self.inputDataS)

        self.showImS = np.fliplr(np.transpose(self.inputDataS))

        # binarization of image
        thr = np.float(self.intThresEdit.text())
        self.mask = self.inputDataS < self.meanS + thr*self.stdS
        self.showMask = np.fliplr(np.transpose(self.mask))

    def ringFinder(self, show=True, batch=False):
        """RingFinder handles the input data, and then evaluates every subimg
        using the given algorithm which decides if there are rings or not.
        Subsequently gives the output data and plots it"""

        if self.corrButton.isChecked() or batch:

            self.corrResult.clear()
            self.ringResult.clear()

            # shape the data into the subimg that we need for the analysis
            nblocks = np.array(self.inputData.shape)/self.n
            blocksInput = tools.blockshaped(self.inputData, *nblocks)
            blocksInputS = tools.blockshaped(self.inputDataS, *nblocks)
            blocksMask = tools.blockshaped(self.mask, *nblocks)

            # for each subimg, we apply the correlation method for ring finding
            intThr = np.float(self.intThresEdit.text())
            minLen = np.float(self.lineLengthEdit.text())/self.pxSize
            thetaStep = np.float(self.thetaStepEdit.text())
            deltaTh = np.float(self.deltaThEdit.text())
            wvlen = np.float(self.wvlenEdit.text())/self.pxSize
            sinPow = np.float(self.sinPowerEdit.text())
            cArgs = minLen, thetaStep, deltaTh, wvlen, sinPow

            # Single-core code
            self.localCorr = np.zeros(len(blocksInput))
            for i in np.arange(len(blocksInput)):
                block = blocksInput[i]
                blockS = blocksInputS[i]
                mask = blocksMask[i]
                # Block may be excluded from the analysis for two reasons.
                # Firstly, because the intensity for all its pixels may be
                # too low. Secondly, because the part of the block that
                # belongs toa neuron may be below an arbitrary 30% of the
                # block. We apply intensity threshold to smoothed data so we
                # don't catch tiny bright spots outside neurons
                neuronFrac = 1 - np.sum(mask)/np.size(mask)
                thres = self.meanS + intThr*self.stdS
                if np.any(blockS > thres) and neuronFrac > 0.25:
                    output = tools.corrMethod(block, mask, *cArgs)
                    angle, corrTheta, corrMax, theta, phase = output
                    # Store results
                    self.localCorr[i] = corrMax
                else:
                    self.localCorr[i] = np.nan

            self.localCorr = self.localCorr.reshape(*self.n)
            self.updateGUI(self.localCorr)

        else:
            self.corrResult.clear()
            self.ringResult.clear()

    def updateGUI(self, localCorr):

        self.analyzed = True
        self.localCorr = localCorr

        # code for visualization of the output
        mag = np.array(self.inputData.shape)/self.n
        self.localCorrBig = np.repeat(self.localCorr, mag[0], 0)
        self.localCorrBig = np.repeat(self.localCorrBig, mag[1], 1)
        showIm = 100*np.fliplr(np.transpose(self.localCorrBig))
        self.corrResult.setImage(np.nan_to_num(showIm))
        self.corrResult.setZValue(10)    # make sure this image is on top
        self.corrResult.setOpacity(0.5)

        self.corrThres = float(self.corrThresEdit.text())
        self.ringsBig = np.nan_to_num(self.localCorrBig) > self.corrThres
        self.ringsBig = self.ringsBig.astype(float)
        self.ringResult.setImage(np.fliplr(np.transpose(self.ringsBig)))
        self.ringResult.setZValue(10)    # make sure this image is on top
        self.ringResult.setOpacity(0.5)

        if self.showCorrMapCheck.isChecked():
            plt.figure(figsize=(10, 8))
            data = self.localCorr.reshape(*self.n)
            data = np.flipud(data)
            maskedData = np.ma.array(data, mask=np.isnan(data))
            heatmap = plt.pcolor(maskedData, cmap='inferno')
            for y in range(data.shape[0]):
                for x in range(data.shape[1]):
                    plt.text(x + 0.5, y + 0.5, '%.4f' % data[y, x],
                             horizontalalignment='center',
                             verticalalignment='center',)
            plt.colorbar(heatmap)
            plt.show()

    def batch(self, function, tech):
        try:
            filenames = utils.getFilenames('Load ' + tech + ' images',
                                           [('Tiff file', '.tif')],
                                           self.initialdir)
            nfiles = len(filenames)
            function(filenames[0])
            corrArray = np.zeros((nfiles, self.n[0], self.n[1]))

            # Expand correlation array so it matches data shape
            corrExp = np.empty((nfiles, self.initShape[0], self.initShape[1]),
                               dtype=np.single)
            corrExp[:] = np.nan
            ringsExp = np.empty((nfiles, self.initShape[0], self.initShape[1]),
                                dtype=np.single)
            ringsExp[:] = np.nan

            path = os.path.split(filenames[0])[0]
            folder = os.path.split(path)[1]
            self.folderStatus.setText('Processing folder ' + path)
            print('Processing folder', path)
            t0 = time.time()
            for i in np.arange(nfiles):
                print(os.path.split(filenames[i])[1])
                self.fileStatus.setText(os.path.split(filenames[i])[1])
                function(filenames[i])
                self.ringFinder(False, batch=True)
                corrArray[i] = self.localCorr

                bound = (np.array(self.initShape) - self.crop).astype(np.int)
                corrExp[i, self.crop:bound[0],
                        self.crop:bound[1]] = self.localCorrBig

                # Save correlation values array
                corrName = utils.insertSuffix(filenames[i], '_correlation')
                tiff.imsave(corrName, corrExp[i], software='Gollum',
                            imagej=True,
                            resolution=(1000/self.pxSize, 1000/self.pxSize),
                            metadata={'spacing': 1, 'unit': 'um'})

            # Saving ring images
            ringsExp[corrExp < self.corrThres] = 0
            ringsExp[corrExp >= self.corrThres] = 1
            for i in np.arange(nfiles):
                # Save correlation values array
                ringName = utils.insertSuffix(filenames[i], '_rings')
                tiff.imsave(ringName, ringsExp[i], software='Gollum',
                            imagej=True,
                            resolution=(1000/self.pxSize, 1000/self.pxSize),
                            metadata={'spacing': 1, 'unit': 'um'})

            # plot histogram of the correlation values
            hrange = (np.min(np.nan_to_num(corrArray)),
                      np.max(np.nan_to_num(corrArray)))
            y, x, _ = plt.hist(corrArray.flatten(), bins=60, range=hrange)
            x = (x[1:] + x[:-1])/2

            # Save data array as txt
            corrArrayFlat = corrArray.flatten()
            validCorr = corrArrayFlat[~np.isnan(corrArrayFlat)]
            validArr = np.repeat(np.arange(nfiles), np.prod(self.n))
            validArr = validArr[~np.isnan(corrArrayFlat)]
            valuesTxt = os.path.join(path, folder + 'corr_values.txt')
            np.savetxt(valuesTxt, np.stack((validCorr, validArr), 1),
                       fmt='%f\t%i')

            # Plotting
            plt.figure(0)
            ringData = validCorr[validCorr > self.corrThres]
            n = corrArray.size - np.count_nonzero(np.isnan(corrArray))
            nring = np.sum(validCorr > self.corrThres)
            ringFrac = nring / n
            ringStd = math.sqrt(ringFrac*(1 - ringFrac)/n)
            plt.bar(x, y, align='center', width=(x[1] - x[0]))
            plt.plot((self.corrThres, self.corrThres), (0, np.max(y)), 'r--',
                     linewidth=2)
            text = ('ringFrac={0:.3f} +- {1:.3f} \n'
                    'correlation threshold={2:.2f} \n'
                    'mean correlation={3:.4f} +- {4:.4f} \n'
                    'mean ring correlation={5:.4f} +- {6:.4f}')
            text = text.format(ringFrac, ringStd, self.corrThres,
                               np.mean(validCorr), np.std(validCorr)/n,
                               np.mean(ringData), np.std(ringData)/nring)
            plt.text(0.8*plt.axis()[1], 0.8*plt.axis()[3], text,
                     horizontalalignment='center', verticalalignment='center',
                     bbox=dict(facecolor='white'))
            plt.title("Correlations Histogram")
            plt.xlabel("Value")
            plt.ylabel("Frequency")
            plt.savefig(os.path.join(path, folder + 'corr_hist'))
            plt.close()

            folder = os.path.split(path)[1]
            text = 'Folder ' + folder + ' done in {0:.0f} seconds'
            print(text.format(time.time() - t0))
            self.folderStatus.setText(text.format(time.time() - t0))
            self.fileStatus.setText('                 ')

        except IndexError:
            self.fileStatus.setText('No file selected!')

    def batchSTORM(self):
        self.batch(self.loadSTORM, 'STORM')

    def batchSTED(self):
        self.batch(self.loadSTED, 'STED')

if __name__ == '__main__':
    app = QtGui.QApplication([])
    win = Gollum()
    win.show()
    app.exec_()
