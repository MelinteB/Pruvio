import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import CropEditor,{cropToImagePixels,imageCropFrame,moveCrop} from './CropEditor';

afterEach(()=>{cleanup();vi.restoreAllMocks()});

describe('Receipt crop preview and export geometry',()=>{
  it('fits a tall receipt to 500 px max height without changing aspect ratio',()=>{
    expect(imageCropFrame(1200,2400)).toEqual({aspectRatio:'1200 / 2400',maxWidth:250});
    expect(imageCropFrame(600,300)).toEqual({aspectRatio:'600 / 300',maxWidth:1000});
    expect(imageCropFrame(0,300)).toBeNull();
  });
  it('maps the selected area to precisely bounded source image pixels',()=>{
    expect(cropToImagePixels({x:25,y:50,w:50,h:25},1200,2400))
      .toEqual({sx:300,sy:1200,sw:600,sh:600});
    expect(cropToImagePixels({x:0,y:0,w:100,h:100},1200,2400))
      .toEqual({sx:0,sy:0,sw:1200,sh:2400});
    expect(cropToImagePixels({x:90,y:90,w:30,h:30},1200,2400))
      .toEqual({sx:1080,sy:2160,sw:120,sh:240});
  });
  it('keeps the crop overlay on the same sized frame as the original image',()=>{
    const crop={x:10,y:20,w:70,h:40};
    render(<CropEditor preview="blob:receipt-test" crop={crop} onChange={vi.fn()}/>);
    const image=screen.getByRole('img',{name:'Receipt preview'});
    Object.defineProperty(image,'naturalWidth',{configurable:true,value:1200});
    Object.defineProperty(image,'naturalHeight',{configurable:true,value:2400});
    fireEvent.load(image);
    const stage=image.closest('.crop-stage');
    expect(stage).toBeTruthy();
    expect(stage.style.maxWidth).toBe('250px');
    expect(stage.style.aspectRatio).toBe('1200 / 2400');
    const overlay=stage.querySelector('.crop-overlay');
    expect(overlay).toBeTruthy();
    expect(overlay.style.left).toBe('10%');
    expect(overlay.style.top).toBe('20%');
    expect(overlay.style.width).toBe('70%');
    expect(overlay.style.height).toBe('40%');
  });
  it('uses the correct dimensions after changing to a differently shaped receipt',()=>{
    const crop={x:0,y:0,w:100,h:100};
    const {rerender}=render(<CropEditor preview="blob:tall" crop={crop} onChange={vi.fn()}/>);
    let image=screen.getByRole('img',{name:'Receipt preview'});
    Object.defineProperty(image,'naturalWidth',{configurable:true,value:1200});
    Object.defineProperty(image,'naturalHeight',{configurable:true,value:2400});
    fireEvent.load(image);
    expect(image.closest('.crop-stage').style.maxWidth).toBe('250px');
    rerender(<CropEditor preview="blob:wide" crop={crop} onChange={vi.fn()}/>);
    image=screen.getByRole('img',{name:'Receipt preview'});
    expect(image.closest('.crop-stage').querySelector('.crop-overlay')).toBeNull();
    Object.defineProperty(image,'naturalWidth',{configurable:true,value:2000});
    Object.defineProperty(image,'naturalHeight',{configurable:true,value:1000});
    fireEvent.load(image);
    expect(image.closest('.crop-stage').style.maxWidth).toBe('1000px');
  });
  it('does not move a selected rectangle outside the image boundaries',()=>{
    expect(moveCrop({x:75,y:65,w:25,h:35},30,30)).toEqual({x:75,y:65,w:25,h:35});
  });
});
