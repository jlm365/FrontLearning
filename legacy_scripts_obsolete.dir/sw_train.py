#!/anaconda2/bin/python2.7
u"""
sw_train.py
by Yara Mohajerani (09/2018)

Use a sliding window approach to train NN for glacier fronts

Update History
    09/2018 Written
"""

import os
import numpy as np
import keras
from keras.preprocessing import image
import imp
import sys
import random
from glob import glob
from PIL import Image
from keras import backend as K
from tensorflow.python.client import device_lib
import tensorflow as tf
from sklearn.utils import class_weight

#-- Print backend information
print 'device information: ', device_lib.list_local_devices()
print 'available GPUs: ', K.tensorflow_backend._get_available_gpus()

#-- read in images
def load_data(suffix,trn_dir,tst_dir,n_windows,HH,HW):
    #-- total pixels from given parameters
    tot_pixels = (2*HH+1)*(2*HW+1)
    #-- make subdirectories for input images
    ddir = {}
    ddir['train'] = trn_dir
    ddir['test'] = tst_dir
    #-- initialize dicttionaries
    images = {} 
    labels = {}
    for d in ['train','test']:
        subdir = os.path.join(ddir[d],'images%s'%(suffix))
        #-- get a list of the input files
        file_list = glob(os.path.join(subdir,'*.png'))
        #-- get just the file names
        files = [os.path.basename(i) for i in file_list]

        #-- read data
        n = len(files)
        #-------------------------------------------------------------------------------------------------------------------------
        #-- now make sliding window data
        #-- note first half is centered on boundaries and the second half is not
        #-------------------------------------------------------------------------------------------------------------------------
        labels[d] = np.zeros(n*n_windows)
        images[d] = np.zeros((n*n_windows, 2*HH + 1 , 2*HW + 1))
        #-- get indices of boundaery for each image and select from them randomly
        for i,f in enumerate(files):
            #-- same file name but different directories for images and labels
            img = np.array(Image.open(os.path.join(subdir,f)).convert('L'))/255.
            lbl = np.array(Image.open(os.path.join(ddir[d],'labels',f.replace('Subset','Front'))).convert('L'))/255.

            #-- take n_window random samples from the image
            ih = np.random.randint(HH,high=img.shape[0]-HH,size=n_windows)
            iw = np.random.randint(HW,high=img.shape[1]-HW,size=n_windows)
            for j in range(n_windows):
                images[d][j] = img[ih[j]-HH:ih[j]+HH+1,iw[j]-HW:iw[j]+HW+1]
                label_box = lbl[ih[j]-HH:ih[j]+HH+1,iw[j]-HW:iw[j]+HW+1]
                count_boundary = np.count_nonzero(label_box==0.)
                #-- mark as boundary if the boundary pixels compose at least 1% of the image
                if count_boundary > 0.01*tot_pixels:
                    labels[d][j] = 1
                else:
                    labels[d][j] = 0

    return [images,labels]


#-- train model on patches of images
def train_model(parameters):
    glacier = parameters['GLACIER_NAME']
    suffix = parameters['SUFFIX']
    HW = np.int(parameters['HALF_WIDTH']) 
    HH = np.int(parameters['HALF_HEIGHT'])
    n_windows = np.int(parameters['N_WINDOWS'])
    EPOCHS = np.int(parameters['EPOCHS'])
    BATCHES = np.int(parameters['BATCHES'])
    n_relu = np.int(parameters['N_RELU'])
    imb_w = np.int(parameters['IMBALANCE_RATIO'])

    #-- directory setup
    #- current directory
    current_dir = os.path.dirname(os.path.realpath(__file__))
    ddir = os.path.join(current_dir,'%s.dir'%glacier)
    data_dir = os.path.join(ddir, 'data')
    trn_dir = os.path.join(data_dir,'train')
    tst_dir = os.path.join(data_dir,'test')

    #-- load images
    [images,labels] = load_data(suffix,trn_dir,tst_dir,n_windows,HH,HW)


    #-- set up model
    model = keras.Sequential([
        keras.layers.Flatten(input_shape=(2*HH+1, 2*HW+1)),
        keras.layers.Dense(n_relu, activation=tf.nn.relu),
        keras.layers.Dense(2, activation=tf.nn.softmax)
    ])

    #-- set up class weight to deal with imbalance
    if imb_w == 0:
        class_weights = dict(enumerate(class_weight.compute_class_weight('balanced',
            np.unique(labels['train']),labels['train'])))
    else:
        class_weights = {0: 1.,1: imb_w}

    print class_weights

    #-- checkpoint file
    chk_file = os.path.join(ddir,'SW_frontlearn_weights_%ibtch_%iepochs_%iHH_%iHW_%inwindows_%irelu_%iimbalance%s.h5'\
        %(BATCHES,EPOCHS,HH,HW,n_windows,n_relu,imb_w,suffix))

    #-- if file exists, just read model from file
    if os.path.isfile(chk_file):
        print('Check point exists; loading model from file.')
        # load weights
        model.load_weights(chk_file)

        if parameters['RETRAIN'] in ['y','Y']:
            #-- continue Training
            #-- create checkpoint
            model_checkpoint = keras.callbacks.ModelCheckpoint(chk_file, monitor='loss',\
                verbose=1, save_best_only=True)
            #-- now fit the model
            model.fit(images['train'],labels['train'],batch_size=BATCHES, epochs=EPOCHS, verbose=1,\
                validation_split=0.1, shuffle=True,class_weight=class_weights,callbacks=[model_checkpoint])
        else:
            # Compile model
            model.compile(optimizer='adam', 
                loss='sparse_categorical_crossentropy',
                metrics=['accuracy'])
    #-- if not train model
    else:
        print('Did not find check points. Training model...')
        #-- create checkpoint
        model_checkpoint = keras.callbacks.ModelCheckpoint(chk_file, monitor='loss',\
            verbose=1, save_best_only=True)

        # Compile model
        model.compile(optimizer='adam', 
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy'])
        #-- now fit the model
        model.fit(images['train'],labels['train'],batch_size=BATCHES, epochs=EPOCHS, verbose=1,\
            validation_split=0.1, shuffle=True,class_weight=class_weights,callbacks=[model_checkpoint])

    print('Model is trained. Running on test data...')

    #-- test accuracy
    test_loss, test_acc = model.evaluate(images['test'], labels['test'])
    print('Test accuracy:', test_acc)


#-- main function to get parameters and pass them along to fitting function
def main():
    if (len(sys.argv) == 1):
        sys.exit('You need to input at least one parameter file to set run configurations.')
    else:
        #-- Input Parameter Files (sys.argv[0] is the python code)
        input_files = sys.argv[1:]
        #-- for each input parameter file
        for file in input_files:
            #-- keep track of progress
            print(os.path.basename(file))
            #-- variable with parameter definitions
            parameters = {}
            #-- Opening parameter file and assigning file ID number (fid)
            fid = open(file, 'r')
            #-- for each line in the file will extract the parameter (name and value)
            for fileline in fid:
                #-- Splitting the input line between parameter name and value
                part = fileline.split()
                #-- filling the parameter definition variable
                parameters[part[0]] = part[1]
            #-- close the parameter file
            fid.close()

            #-- pass parameters to training function
            train_model(parameters)

if __name__ == '__main__':
    main()