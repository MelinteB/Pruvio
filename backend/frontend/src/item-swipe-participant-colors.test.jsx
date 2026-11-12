import React from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {itemShareGradient,itemSharePreviewGradient,participantColors} from './participant-colors';
import ItemSwipeGesture from './ItemSwipeGesture';

afterEach(()=>cleanup());

const colors=participantColors([
  {participant_id:1,display_name:'Owner'},
  {participant_id:2,display_name:'Guest'}
]);
const item={
  item_id:5,name:'Coffee',quantity:4,
  assignments:[{participant_id:2,quantity:1,assignment_id:101}]
};

describe('Pruvs item gesture participant-color continuity',()=>{
  it('previews the selecting participant color without losing another participant color',()=>{
    const before=itemShareGradient(item,colors);
    const preview=itemSharePreviewGradient(item,colors,1,2);
    expect(before).toContain(colors['2'].soft);
    expect(preview).toContain(colors['1'].soft);
    expect(preview).toContain(colors['2'].soft);
    expect(preview).toContain('25.00%');
    expect(item.assignments).toHaveLength(1);
    expect(item.assignments[0].quantity).toBe(1);
  });

  it('removing the current participant selection keeps other participant colors',()=>{
    const allocated={...item,assignments:[
      {participant_id:1,quantity:2},
      {participant_id:2,quantity:1}
    ]};
    const preview=itemSharePreviewGradient(allocated,colors,1,0);
    expect(preview).toContain(colors['2'].soft);
    expect(preview).not.toContain(colors['1'].soft);
    expect(itemSharePreviewGradient(allocated,colors,1,2)).toContain(colors['1'].soft);
  });

  it('live swipe preview uses participant colors rather than a green overlay',()=>{
    const onSelect=vi.fn();
    const {container}=render(<ItemSwipeGesture
      item={item} own={0} max={3} step={1} disabled={false}
      participantId={1} colors={colors} className="item"
      onSelect={onSelect} style={{'--item-share-background':itemShareGradient(item,colors)}}>
       <button type="button">Add</button>
    </ItemSwipeGesture>);
    const card=container.querySelector('.pruvs-v7151-swipe-card');
    vi.spyOn(card,'getBoundingClientRect').mockReturnValue({
      left:0,right:300,top:0,bottom:100,width:300,height:100
    });
    fireEvent.pointerDown(card,{pointerId:1,button:0,clientX:10,clientY:20});
    fireEvent.pointerMove(card,{pointerId:1,clientX:210,clientY:20});
    const gradient=card.style.getPropertyValue('--item-share-background');
    expect(gradient).toContain(colors['1'].soft);
    expect(gradient).toContain(colors['2'].soft);
    expect(container.querySelector('.pruvs-v7151-gesture-progress')).toBeNull();
    expect(screen.queryByRole('button',{name:'Half'})).toBeNull();
    expect(screen.queryByRole('button',{name:'All'})).toBeNull();
    fireEvent.pointerUp(card,{pointerId:1,clientX:210,clientY:20});
    expect(onSelect).toHaveBeenCalledWith(2);
    expect(card.style.getPropertyValue('--item-share-background')).toContain(colors['2'].soft);
  });
});
