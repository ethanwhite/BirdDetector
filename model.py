#Subclass deepforest model to allow empty batches and datasets
from deepforest import main
import os
import pandas as pd
import numpy as np
from torch.utils.data import Dataset
import albumentations as A
from albumentations.pytorch import ToTensorV2
import torch
from PIL import Image
import random

def collate_fn(batch):
    batch = list(filter(lambda x : x is not None, batch))
        
    return tuple(zip(*batch))


def get_transform(augment):
    """Albumentations transformation of bounding boxs"""
    if augment:
        transform = A.Compose([
            A.HorizontalFlip(p=0.5),
            ToTensorV2()
        ], bbox_params=A.BboxParams(format='pascal_voc',label_fields=["category_ids"]))
        
    else:
        transform = A.Compose([ToTensorV2()])
        
    return transform

class BirdDataset(Dataset):

    def __init__(self, csv_file, root_dir, transforms=None, label_dict = {"Bird": 0}, train=True):
        """
        Args:
            csv_file (string): Path to a single csv file with annotations.
            root_dir (string): Directory with all the images.
            transform (callable, optional): Optional transform to be applied
                on a sample.
            label_dict: a dictionary where keys are labels from the csv column and values are numeric labels "Tree" -> 0
        Returns:
            If train:
                path, image, targets
            else:
                image
        """
        self.annotations = pd.read_csv(csv_file)
        self.root_dir = root_dir
        if transforms is None:
            self.transform = get_transform(augment=train)
        else:
            self.transform = transforms
        self.image_names = self.annotations.image_path.unique()
        self.label_dict = label_dict
        self.train = train

    def __len__(self):
        return len(self.image_names)

    def __getitem__(self, idx):
        img_name = os.path.join(self.root_dir, self.image_names[idx])
        #read, scale and set to float
        image = np.array(Image.open(img_name).convert("RGB"))/255
        image = image.astype("float32")

        if self.train:
            # select annotations
            image_annotations = self.annotations[self.annotations.image_path ==
                                                 self.image_names[idx]]
            targets = {}
            targets["boxes"] = image_annotations[["xmin", "ymin", "xmax",
                                                  "ymax"]].values.astype(float)
            
            # Labels need to be encoded
            targets["labels"] = image_annotations.label.apply(
                lambda x: self.label_dict[x]).values.astype(int)
    
            #Check for blank tensors
            augmented = self.transform(image=image, bboxes=targets["boxes"], category_ids=targets["labels"])
            image = augmented["image"]
            
            boxes = np.array(augmented["bboxes"])
            boxes = torch.from_numpy(boxes)
            labels = np.array(augmented["category_ids"]) 
            labels = torch.from_numpy(labels)
            targets = {"boxes":boxes,"labels":labels}   
            
            #debug, manually remove a blank tensor
            if self.image_names[idx] == "46544951_2.png":
                targets["boxes"] = torch.empty(0,4)
                
            #Check for blank tensors, if blank shuffle to new position
            all_empty = all([len(x) == 0 for x in targets["boxes"]])
            if all_empty:
                print("Blank augmentation, returning random index")
                return self.__getitem__(random.choice(range(self.__len__())))
            
            return self.image_names[idx], image, targets
            
        else:
            augmented = self.transform(image=image)
            return augmented["image"]
            

class BirdDetector(main.deepforest):
    def __init__(self,transforms=None):
        super(BirdDetector, self).__init__(num_classes=1, label_dict={"Bird":0},transforms=transforms)
    
    def load_dataset(self,
                     csv_file,
                     root_dir=None,
                     augment=False,
                     shuffle=True,
                     batch_size=1):
        """Create a tree dataset for inference
        Csv file format is .csv file with the columns "image_path", "xmin","ymin","xmax","ymax" for the image name and bounding box position.
        Image_path is the relative filename, not absolute path, which is in the root_dir directory. One bounding box per line.

        Args:
            csv_file: path to csv file
            root_dir: directory of images. If none, uses "image_dir" in config
            augment: Whether to create a training dataset, this activates data augmentations
        Returns:
            ds: a pytorch dataset
        """

        ds = BirdDataset(csv_file=csv_file,
                                 root_dir=root_dir,
                                 transforms=self.transforms(augment=augment),
                                 label_dict=self.label_dict)

        data_loader = torch.utils.data.DataLoader(
            ds,
            batch_size=batch_size,
            shuffle=shuffle,
            collate_fn=collate_fn,
            num_workers=self.config["workers"],
        )

        return data_loader        