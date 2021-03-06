# https://github.com/sbarratt/inception-score-pytorch/blob/master/inception_score.py

import torch
import numpy as np
from torch import nn
from torch.nn import functional as F
import torch.utils.data

from torchvision.models.inception import inception_v3

from metrics.inception import InceptionV3

from tqdm import tqdm

# FIX: classifier
def inception_score(imgs, cuda=True, batch_size=32, resize=False, splits=1, classifier=None, log_logit=False, requires_grad=False):
    """Computes the inception score of the generated images imgs

    imgs -- Torch dataset of (3xHxW) numpy images normalized in the range [-1, 1]
    cuda -- whether or not to run on GPU
    batch_size -- batch size for feeding into Classifier
    splits -- number of splits
    """

    if cuda:
        device = torch.device('cuda:0')
    else:
        device = torch.device('cpu')

    N = len(imgs)

    assert batch_size > 0
    assert N > batch_size

    # Set up dtype
    if cuda:
        dtype = torch.cuda.FloatTensor
    else:
        if torch.cuda.is_available():
            print("WARNING: You have a CUDA device, so you should probably set cuda=True")
        dtype = torch.FloatTensor

    # Set up dataloader
    dataloader = torch.utils.data.DataLoader(imgs, batch_size=batch_size)

    ### Load pretrained classifier
    if classifier is None:
        # Load inception model
        block_idx = InceptionV3.BLOCK_INDEX_BY_DIM['prob']
        model = InceptionV3([block_idx], requires_grad=requires_grad).to(device)
        model.eval()

        upsample = torch.nn.Upsample((299,299),mode='bilinear',align_corners=False)
        def get_pred(x):
            if resize:
                x = upsample(x)
            return model(x)
    else:
        classifier.eval()
        def get_pred(x):
            x = classifier(x)
            if log_logit:
                out = x.exp()
            else:
                out = x
            if requires_grad == False:
                out = out.data
            return out

    # Get predictions
    output_sample = next(iter(dataloader))
    if cuda:
        output_sample = output_sample.cuda()
    output_shape = get_pred(output_sample)[0].shape
    preds = torch.zeros((N, output_shape[-1]))

    for i, batch in enumerate(tqdm(dataloader), 0):
        batch = batch.type(dtype)
        batch_size_i = batch.size()[0]
        if cuda:
            batch = batch.cuda()

        preds[i*batch_size:i*batch_size + batch_size_i] = get_pred(batch)[0].cpu()
    
    # Now compute the mean kl-div
    split_scores = torch.zeros(splits)

    kl_d = torch.nn.KLDivLoss(reduction='sum')

    for k in range(splits):
        part = preds[k * (N // splits): (k+1) * (N // splits), :]
        py = torch.mean(part, axis=0)
        scores = torch.zeros(part.shape[0])
        for i in range(part.shape[0]):
            pyx = part[i, :]
            scores[i] = kl_d(py.log(),pyx)
        split_scores[k] = torch.exp(torch.mean(scores))

    return torch.mean(split_scores), torch.std(split_scores)

if __name__ == '__main__':
    class IgnoreLabelDataset(torch.utils.data.Dataset):
        def __init__(self, orig):
            self.orig = orig

        def __getitem__(self, index):
            return self.orig[index][0]

        def __len__(self):
            return len(self.orig)

    import torchvision.datasets as dset
    import torchvision.transforms as transforms

    cifar = dset.CIFAR10(root='./data/cifar10', download=True,
    train=False,
                             transform=transforms.Compose([
                                 transforms.ToTensor(),
                             ])
    )
    
    IgnoreLabelDataset(cifar)
    
    print(len(cifar))

    print ("Calculating Inception Score...")
    print (inception_score(IgnoreLabelDataset(cifar), cuda=True, batch_size=200, resize=True, splits=1))
